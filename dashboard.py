from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal, Optional
from urllib.parse import urlencode, urlparse

import aiohttp
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session, session_scope
from economy import get_player_profile, get_transaction_history_page, record_transaction
from models import (
    Account,
    AdminAuditLog,
    Bank,
    AdminRoleGrant,
    AdminUserGrant,
    DashboardSession,
    EconomyTransaction,
    Player,
)

logger = logging.getLogger("fihcoin.dashboard")
router = APIRouter()

DISCORD_API = "https://discord.com/api/v10"
SESSION_COOKIE = "fihcoin_dashboard_session"
STATE_COOKIE = "fihcoin_oauth_state"
SESSION_LIFETIME = timedelta(days=7)
OAUTH_STATE_LIFETIME = 600
ADMINISTRATOR_PERMISSION = 1 << 3
MAX_BALANCE = Decimal("999999999999999999.99")


def _environment(name: str) -> str:
    return os.getenv(name, "").strip()


def _guild_id() -> int:
    value = _environment("RELEASE_GUILD_ID") or _environment("DISCORD_GUILD_ID")
    try:
        guild_id = int(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard guild is not configured.",
        )
    if guild_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard guild is not configured.",
        )
    return guild_id


def _oauth_config() -> tuple[str, str, str, str, str]:
    client_id = _environment("DISCORD_CLIENT_ID")
    client_secret = _environment("DISCORD_CLIENT_SECRET")
    session_secret = _environment("DASHBOARD_SESSION_SECRET")
    api_url = _environment("DASHBOARD_API_URL").rstrip("/")
    frontend_url = _environment("DASHBOARD_FRONTEND_URL").rstrip("/")
    if not all((client_id, client_secret, session_secret, api_url, frontend_url)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard authentication is not configured.",
        )
    if len(session_secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard session secret must be at least 32 characters.",
        )
    for configured_url in (api_url, frontend_url):
        parsed_url = urlparse(configured_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.path not in {"", "/"}
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dashboard URLs must be valid public origins.",
            )
        if parsed_url.scheme != "https" and parsed_url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dashboard URLs must use HTTPS outside local development.",
            )
    return client_id, client_secret, session_secret, api_url, frontend_url


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _signed_state(state: str, verifier: str, secret: str) -> str:
    payload = json.dumps(
        {"state": state, "verifier": verifier, "expires": int(datetime.now(timezone.utc).timestamp()) + OAUTH_STATE_LIFETIME},
        separators=(",", ":"),
    ).encode()
    encoded = _b64encode(payload)
    signature = _b64encode(hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def _verify_state(cookie: Optional[str], supplied_state: str, secret: str) -> str:
    if not cookie or "." not in cookie:
        raise HTTPException(status_code=400, detail="Invalid or expired Discord login state.")
    encoded, signature = cookie.rsplit(".", 1)
    expected = _b64encode(hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=400, detail="Invalid or expired Discord login state.")
    try:
        payload = json.loads(_b64decode(encoded))
        if (
            not hmac.compare_digest(str(payload["state"]), supplied_state)
            or int(payload["expires"]) < int(datetime.now(timezone.utc).timestamp())
        ):
            raise ValueError
        verifier = str(payload["verifier"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid or expired Discord login state.")
    return verifier


def _session_cookie_options(api_url: str, frontend_url: str) -> dict[str, Any]:
    api_host = urlparse(api_url).hostname
    frontend_host = urlparse(frontend_url).hostname
    secure = urlparse(api_url).scheme == "https"
    cross_site = api_host != frontend_host
    return {
        "secure": secure,
        "samesite": "none" if secure and cross_site else "lax",
    }


def _csrf_token(session_token: str) -> str:
    return hmac.new(
        session_token.encode(),
        b"fihcoin-dashboard-csrf",
        hashlib.sha256,
    ).hexdigest()


def _require_csrf(request: Request, csrf_header: Optional[str]) -> None:
    session_token = request.cookies.get(SESSION_COOKIE, "")
    expected = _csrf_token(session_token)
    if not csrf_header or not hmac.compare_digest(csrf_header, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")


async def _discord_request(
    request: Request,
    path: str,
    *,
    params: Optional[dict[str, str]] = None,
    not_found_ok: bool = False,
) -> Any:
    bot_token = _environment("DISCORD_TOKEN")
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discord membership verification is not configured.",
        )

    client: aiohttp.ClientSession = request.app.state.http_session
    try:
        async with client.get(
            f"{DISCORD_API}{path}",
            headers={"Authorization": f"Bot {bot_token}"},
            params=params,
        ) as response:
            if response.status == 404 and not_found_ok:
                return None
            if response.status >= 400:
                logger.warning("Discord API membership check failed with HTTP %s.", response.status)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Could not verify current Discord server membership.",
                )
            return await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        logger.exception("Could not reach Discord while verifying dashboard access.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discord membership verification is temporarily unavailable.",
        )


async def _current_member(request: Request, guild_id: int, discord_user_id: int) -> Optional[dict[str, Any]]:
    return await _discord_request(
        request,
        f"/guilds/{guild_id}/members/{discord_user_id}",
        not_found_ok=True,
    )


def _has_discord_administrator_permission(
    discord_user_id: int,
    guild: dict[str, Any],
    member: dict[str, Any],
    roles: list[dict[str, Any]],
) -> bool:
    if int(guild.get("owner_id", 0)) == discord_user_id:
        return True

    member_role_ids = {int(role_id) for role_id in member.get("roles", [])}
    for role in roles:
        try:
            if int(role["id"]) in member_role_ids and int(role["permissions"]) & ADMINISTRATOR_PERMISSION:
                return True
        except (KeyError, TypeError, ValueError):
            continue
    return False


async def _has_admin_access(
    request: Request,
    db: AsyncSession,
    guild_id: int,
    discord_user_id: int,
    member: dict[str, Any],
) -> bool:
    user_grant = await db.scalar(
        select(AdminUserGrant.id).where(
            AdminUserGrant.guild_id == guild_id,
            AdminUserGrant.discord_user_id == discord_user_id,
            AdminUserGrant.is_active.is_(True),
        ).limit(1)
    )
    if user_grant is not None:
        return True

    guild, roles = await asyncio.gather(
        _discord_request(request, f"/guilds/{guild_id}"),
        _discord_request(request, f"/guilds/{guild_id}/roles"),
    )
    if _has_discord_administrator_permission(discord_user_id, guild, member, roles):
        return True

    role_ids = [int(role_id) for role_id in member.get("roles", [])]
    if not role_ids:
        return False
    role_grant = await db.scalar(
        select(AdminRoleGrant.id).where(
            AdminRoleGrant.guild_id == guild_id,
            AdminRoleGrant.discord_role_id.in_(role_ids),
            AdminRoleGrant.is_active.is_(True),
        ).limit(1)
    )
    return role_grant is not None


@dataclass
class MemberContext:
    session: DashboardSession
    member: dict[str, Any]


async def get_dashboard_session(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> DashboardSession:
    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in with Discord.")

    token_hash = hashlib.sha256(session_token.encode()).hexdigest()
    dashboard_session = await db.scalar(
        select(DashboardSession).where(DashboardSession.token_hash == token_hash)
    )
    if (
        dashboard_session is None
        or dashboard_session.expires_at <= datetime.now(timezone.utc)
    ):
        if dashboard_session is not None:
            await db.delete(dashboard_session)
            await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired.")
    return dashboard_session


async def get_member_context(
    request: Request,
    dashboard_session: DashboardSession = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_session),
) -> MemberContext:
    member = await _current_member(
        request,
        dashboard_session.guild_id,
        dashboard_session.discord_user_id,
    )
    if member is None:
        await db.delete(dashboard_session)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are no longer a member of the configured Discord server.",
        )
    return MemberContext(session=dashboard_session, member=member)


async def require_admin(
    request: Request,
    context: MemberContext = Depends(get_member_context),
    db: AsyncSession = Depends(get_session),
) -> MemberContext:
    if not await _has_admin_access(
        request,
        db,
        context.session.guild_id,
        context.session.discord_user_id,
        context.member,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access is required.")
    return context


@router.get("/auth/login")
async def login() -> Response:
    client_id, _, session_secret, api_url, _ = _oauth_config()
    _guild_id()
    if not _environment("DISCORD_TOKEN"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discord membership verification is not configured.",
        )
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _b64encode(hashlib.sha256(verifier.encode()).digest())
    redirect_uri = f"{api_url}/auth/callback"
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "identify",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    redirect = RedirectResponse(f"https://discord.com/oauth2/authorize?{params}")
    redirect.set_cookie(
        STATE_COOKIE,
        _signed_state(state, verifier, session_secret),
        max_age=OAUTH_STATE_LIFETIME,
        httponly=True,
        secure=api_url.startswith("https://"),
        samesite="lax",
        path="/auth",
    )
    return redirect


@router.get("/auth/callback")
async def oauth_callback(
    request: Request,
    code: str,
    state: str,
) -> Response:
    client_id, client_secret, session_secret, api_url, frontend_url = _oauth_config()
    verifier = _verify_state(request.cookies.get(STATE_COOKIE), state, session_secret)
    redirect_uri = f"{api_url}/auth/callback"
    client: aiohttp.ClientSession = request.app.state.http_session

    try:
        async with client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as token_response:
            if token_response.status >= 400:
                raise HTTPException(status_code=401, detail="Discord login could not be completed.")
            token_data = await token_response.json()
        async with client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        ) as user_response:
            if user_response.status >= 400:
                raise HTTPException(status_code=401, detail="Discord login could not be completed.")
            discord_user = await user_response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, TypeError):
        logger.exception("Discord OAuth exchange failed.")
        raise HTTPException(status_code=502, detail="Discord login is temporarily unavailable.")

    try:
        discord_user_id = int(discord_user["id"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Discord did not return a valid user profile.")
    guild_id = _guild_id()
    member = await _current_member(request, guild_id, discord_user_id)
    if member is None:
        redirect = RedirectResponse(f"{frontend_url}/?login_error=not_member", status_code=303)
        redirect.delete_cookie(STATE_COOKIE, path="/auth")
        return redirect

    session_token = secrets.token_urlsafe(48)
    dashboard_session = DashboardSession(
        token_hash=hashlib.sha256(session_token.encode()).hexdigest(),
        discord_user_id=discord_user_id,
        guild_id=guild_id,
        expires_at=datetime.now(timezone.utc) + SESSION_LIFETIME,
    )
    async with session_scope() as db:
        async with db.begin():
            db.add(dashboard_session)

    redirect = RedirectResponse(frontend_url, status_code=303)
    cookie_options = _session_cookie_options(api_url, frontend_url)
    redirect.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=cookie_options["secure"],
        samesite=cookie_options["samesite"],
        path="/",
    )
    redirect.delete_cookie(STATE_COOKIE, path="/auth")
    return redirect


@router.get("/auth/me")
async def auth_me(
    request: Request,
    context: MemberContext = Depends(get_member_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    session_token = request.cookies.get(SESSION_COOKIE, "")
    user = context.member.get("user", {})
    return {
        "user": {
            "id": str(context.session.discord_user_id),
            "username": user.get("username", "Discord member"),
            "global_name": user.get("global_name"),
            "avatar_url": _avatar_url(user),
        },
        "guild_id": str(context.session.guild_id),
        "is_admin": await _has_admin_access(
            request,
            db,
            context.session.guild_id,
            context.session.discord_user_id,
            context.member,
        ),
        "csrf_token": _csrf_token(session_token),
    }


@router.post("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    dashboard_session: DashboardSession = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_session),
    csrf_token: Optional[str] = Header(default=None, alias="X-CSRF-Token"),
) -> dict[str, bool]:
    _require_csrf(request, csrf_token)
    await db.delete(dashboard_session)
    await db.commit()
    api_url = _environment("DASHBOARD_API_URL")
    frontend_url = _environment("DASHBOARD_FRONTEND_URL")
    options = _session_cookie_options(api_url, frontend_url) if api_url and frontend_url else {"secure": False, "samesite": "lax"}
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=options["secure"],
        httponly=True,
        samesite=options["samesite"],
    )
    return {"ok": True}


def _avatar_url(user: dict[str, Any]) -> Optional[str]:
    user_id = str(user.get("id", ""))
    avatar = user.get("avatar")
    if not user_id or not avatar:
        return None
    extension = "gif" if str(avatar).startswith("a_") else "png"
    return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.{extension}?size=128"


def _member_name(member: dict[str, Any]) -> str:
    user = member.get("user", {})
    return member.get("nick") or user.get("global_name") or user.get("username") or str(user.get("id", "Member"))


@router.get("/api/me")
async def member_dashboard(
    context: MemberContext = Depends(get_member_context),
) -> dict[str, Any]:
    user = context.member.get("user", {})
    wallet, bank, total, rank, created_at, transaction_count = await get_player_profile(
        context.session.guild_id,
        context.session.discord_user_id,
    )
    return {
        "user": {
            "id": str(context.session.discord_user_id),
            "name": _member_name(context.member),
            "username": user.get("username", "Discord member"),
            "avatar_url": _avatar_url(user),
        },
        "balances": {
            "wallet": str(wallet),
            "bank": str(bank),
            "total": str(total),
        },
        "rank": rank,
        "account_created_at": created_at.isoformat(),
        "transaction_count": transaction_count,
    }


@router.get("/api/me/transactions")
async def member_transactions(
    context: MemberContext = Depends(get_member_context),
    limit: int = Query(default=10, ge=1, le=25),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    transactions, total = await get_transaction_history_page(
        context.session.guild_id,
        context.session.discord_user_id,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [
            {
                "id": str(transaction.id),
                "type": transaction.transaction_type,
                "amount": str(transaction.amount),
                "fee": str(transaction.fee),
                "note": transaction.note,
                "sender_id": str(transaction.sender_discord_id) if transaction.sender_discord_id else None,
                "recipient_id": str(transaction.recipient_discord_id) if transaction.recipient_discord_id else None,
                "created_at": transaction.created_at.isoformat(),
            }
            for transaction in transactions
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/admin/overview")
async def admin_overview(
    context: MemberContext = Depends(require_admin),
) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    async with session_scope() as db:
        player_count = await db.scalar(
            select(func.count(Player.id)).where(Player.guild_id == context.session.guild_id)
        )
        totals = await db.execute(
            select(
                func.coalesce(
                    func.sum(case((Account.account_type == "wallet", Account.balance), else_=0)),
                    0,
                ).label("wallet_total"),
                func.coalesce(
                    func.sum(case((Account.account_type == "bank", Account.balance), else_=0)),
                    0,
                ).label("bank_total"),
            )
            .join(Player, Account.player_id == Player.id)
            .where(Player.guild_id == context.session.guild_id)
        )
        wallet_total, bank_total = totals.one()
        shared_bank_total = await db.scalar(
            select(func.coalesce(func.sum(Bank.balance), 0)).where(
                Bank.guild_id == context.session.guild_id
            )
        )
        recent_count, recent_volume = (
            await db.execute(
                select(
                    func.count(EconomyTransaction.id),
                    func.coalesce(func.sum(EconomyTransaction.amount), 0),
                ).where(
                    EconomyTransaction.guild_id == context.session.guild_id,
                    EconomyTransaction.created_at >= since,
                )
            )
        ).one()
        recent = await db.scalars(
            select(EconomyTransaction)
            .where(EconomyTransaction.guild_id == context.session.guild_id)
            .order_by(EconomyTransaction.created_at.desc(), EconomyTransaction.id.desc())
            .limit(8)
        )

    recent_items = [
        {
            "id": str(item.id),
            "type": item.transaction_type,
            "amount": str(item.amount),
            "created_at": item.created_at.isoformat(),
            "actor_id": str(item.actor_discord_id) if item.actor_discord_id else None,
        }
        for item in recent
    ]
    return {
        "members": int(player_count or 0),
        "wallet_total": str(wallet_total),
        "bank_total": str(bank_total),
        "shared_bank_total": str(shared_bank_total or 0),
        "circulation": str(wallet_total + bank_total + (shared_bank_total or 0)),
        "transactions_24h": int(recent_count or 0),
        "volume_24h": str(recent_volume),
        "recent_transactions": recent_items,
    }


@router.get("/api/admin/members")
async def search_guild_members(
    request: Request,
    context: MemberContext = Depends(require_admin),
    query: str = Query(min_length=2, max_length=64),
) -> dict[str, Any]:
    normalized_query = query.strip()
    if not normalized_query:
        return {"items": []}

    if normalized_query.isdecimal() and len(normalized_query) <= 20:
        member = await _discord_request(
            request,
            f"/guilds/{context.session.guild_id}/members/{normalized_query}",
            not_found_ok=True,
        )
        members = [member] if member else []
    else:
        members = await _discord_request(
            request,
            f"/guilds/{context.session.guild_id}/members/search",
            params={"query": normalized_query, "limit": "25"},
        )

    user_ids: list[int] = []
    for member in members:
        try:
            user_ids.append(int(member["user"]["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not user_ids:
        return {"items": []}

    async with session_scope() as db:
        players = await db.scalars(
            select(Player).where(
                Player.guild_id == context.session.guild_id,
                Player.discord_user_id.in_(user_ids),
            )
        )
        player_by_user = {player.discord_user_id: player for player in players}
        account_rows = await db.execute(
            select(Player.discord_user_id, Account.account_type, Account.balance)
            .join(Account, Account.player_id == Player.id)
            .where(
                Player.guild_id == context.session.guild_id,
                Player.discord_user_id.in_(user_ids),
            )
        )
        balances: dict[int, dict[str, Decimal]] = {}
        for discord_user_id, account_type, balance in account_rows.all():
            balances.setdefault(discord_user_id, {})[account_type] = balance

    items = []
    for member in members:
        user = member.get("user", {})
        try:
            discord_user_id = int(user["id"])
        except (KeyError, TypeError, ValueError):
            continue
        account_balances = balances.get(discord_user_id, {})
        wallet = account_balances.get("wallet", Decimal("0.00"))
        bank = account_balances.get("bank", Decimal("0.00"))
        items.append(
            {
                "id": str(discord_user_id),
                "name": _member_name(member),
                "username": user.get("username", ""),
                "avatar_url": _avatar_url(user),
                "wallet": str(wallet),
                "bank": str(bank),
                "total": str(wallet + bank),
                "has_profile": discord_user_id in player_by_user,
            }
        )
    return {"items": items}


class BalanceSetRequest(BaseModel):
    account_type: Literal["wallet", "bank"]
    balance: Decimal = Field(ge=0, max_digits=20, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A reason is required.")
        return value

    @field_validator("balance")
    @classmethod
    def validate_balance_range(cls, value: Decimal) -> Decimal:
        if value > MAX_BALANCE:
            raise ValueError("Balance exceeds the supported account limit.")
        return value


@router.post("/api/admin/members/{discord_user_id}/balance")
async def set_member_balance(
    discord_user_id: int,
    payload: BalanceSetRequest,
    request: Request,
    context: MemberContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    csrf_token: Optional[str] = Header(default=None, alias="X-CSRF-Token"),
) -> dict[str, Any]:
    _require_csrf(request, csrf_token)
    if discord_user_id <= 0:
        raise HTTPException(status_code=422, detail="Invalid Discord user ID.")

    guild_id = context.session.guild_id
    target_member = await _current_member(request, guild_id, discord_user_id)
    if target_member is None:
        raise HTTPException(status_code=404, detail="The selected user is not a member of this Discord server.")
    await db.execute(
        pg_insert(Player)
        .values(guild_id=guild_id, discord_user_id=discord_user_id)
        .on_conflict_do_nothing(constraint="uq_player_guild_user")
    )
    player = await db.scalar(
        select(Player).where(
            Player.guild_id == guild_id,
            Player.discord_user_id == discord_user_id,
        ).with_for_update()
    )
    if player is None:
        raise HTTPException(status_code=500, detail="Could not load the member's economy profile.")

    await db.execute(
        pg_insert(Account)
        .values(player_id=player.id, account_type=payload.account_type)
        .on_conflict_do_nothing(constraint="uq_account_player_type")
    )
    account = await db.scalar(
        select(Account).where(
            Account.player_id == player.id,
            Account.account_type == payload.account_type,
        ).with_for_update()
    )
    if account is None:
        raise HTTPException(status_code=500, detail="Could not load the selected account.")

    previous_balance = Decimal(account.balance)
    new_balance = payload.balance.quantize(Decimal("0.01"))
    change = new_balance - previous_balance
    transaction: Optional[EconomyTransaction] = None
    if change != 0:
        account.balance = new_balance
        transaction = await record_transaction(
            db,
            guild_id=guild_id,
            transaction_type="admin_balance_set",
            amount=abs(change),
            actor_discord_id=context.session.discord_user_id,
            sender_discord_id=discord_user_id if change < 0 else None,
            recipient_discord_id=discord_user_id if change > 0 else None,
            note=f"Set {payload.account_type} balance: {payload.reason}",
        )
        await db.flush()

    audit = AdminAuditLog(
        guild_id=guild_id,
        actor_discord_id=context.session.discord_user_id,
        action="balance_set",
        target_type="discord_user",
        target_id=str(discord_user_id),
        details={
            "account_type": payload.account_type,
            "previous_balance": str(previous_balance),
            "new_balance": str(new_balance),
            "reason": payload.reason,
            "changed": change != 0,
            "transaction_id": str(transaction.id) if transaction else None,
        },
    )
    db.add(audit)
    await db.commit()

    return {
        "member_id": str(discord_user_id),
        "account_type": payload.account_type,
        "previous_balance": str(previous_balance),
        "balance": str(new_balance),
        "changed": change != 0,
    }
