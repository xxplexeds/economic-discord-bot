"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

type Auth = {
  user: { id: string; username: string; global_name: string | null; avatar_url: string | null };
  is_admin: boolean;
  csrf_token: string;
};

type Dashboard = {
  user: { id: string; name: string; username: string; avatar_url: string | null };
  balances: { wallet: string; bank: string; total: string };
  rank: number;
  account_created_at: string;
  transaction_count: number;
};

type Transaction = {
  id: string;
  type: string;
  amount: string;
  fee: string;
  note: string | null;
  sender_id: string | null;
  recipient_id: string | null;
  created_at: string;
};

type TransactionPage = { items: Transaction[]; total: number; limit: number; offset: number };
type AdminOverview = {
  members: number;
  wallet_total: string;
  bank_total: string;
  shared_bank_total: string;
  circulation: string;
  transactions_24h: number;
  volume_24h: string;
  recent_transactions: Array<{ id: string; type: string; amount: string; created_at: string; actor_id: string | null }>;
};
type AdminMember = {
  id: string;
  name: string;
  username: string;
  avatar_url: string | null;
  wallet: string;
  bank: string;
  total: string;
  has_profile: boolean;
};

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
  } catch {
    throw new Error("Cannot connect to the Fihcoin API. Check NEXT_PUBLIC_API_URL and the API service.");
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Use the HTTP status when the server does not return JSON.
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

function money(value: string) {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return `${value} FC`;
  const [, sign, integer, fraction = ""] = match;
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${sign}${grouped}.${fraction.padEnd(2, "0").slice(0, 2)} FC`;
}

function date(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

export default function Home() {
  const [auth, setAuth] = useState<Auth | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [transactions, setTransactions] = useState<TransactionPage | null>(null);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [members, setMembers] = useState<AdminMember[]>([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<AdminMember | null>(null);
  const [accountType, setAccountType] = useState<"wallet" | "bank">("wallet");
  const [balance, setBalance] = useState("");
  const [reason, setReason] = useState("");
  const [pageOffset, setPageOffset] = useState(0);
  const [busy, setBusy] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loginMessage, setLoginMessage] = useState("");

  const loadPage = useCallback(async (offset = 0) => {
    setBusy(true);
    setError("");
    try {
      const signedIn = await apiRequest<Auth>("/auth/me");
      const [profile, history] = await Promise.all([
        apiRequest<Dashboard>("/api/me"),
        apiRequest<TransactionPage>(`/api/me/transactions?limit=8&offset=${offset}`),
      ]);
      setAuth(signedIn);
      setDashboard(profile);
      setTransactions(history);
      setPageOffset(offset);
      if (signedIn.is_admin) {
        setOverview(await apiRequest<AdminOverview>("/api/admin/overview"));
      } else {
        setOverview(null);
      }
    } catch (requestError) {
      setError(requestError instanceof ApiError && requestError.status === 401 ? "" : errorText(requestError));
      setAuth(null);
      setDashboard(null);
      setTransactions(null);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void loadPage();
  }, [loadPage]);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("login_error") === "not_member") {
      setLoginMessage("This Discord account is not a member of the configured server.");
    }
  }, []);

  async function searchMembers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      const result = await apiRequest<{ items: AdminMember[] }>(
        `/api/admin/members?query=${encodeURIComponent(search.trim())}`,
      );
      setMembers(result.items);
      setSelected(null);
    } catch (requestError) {
      setError(errorText(requestError));
    }
  }

  async function setExactBalance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !auth) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      if (!window.confirm(`Set ${selected.name}'s ${accountType} balance to ${money(balance)}? This replaces the current balance and is recorded in the audit log.`)) {
        return;
      }
      const result = await apiRequest<{ balance: string; account_type: string }>(
        `/api/admin/members/${selected.id}/balance`,
        {
          method: "POST",
          headers: { "X-CSRF-Token": auth.csrf_token },
          body: JSON.stringify({ account_type: accountType, balance, reason }),
        },
      );
      setNotice(`${selected.name}'s ${result.account_type} balance is now ${money(result.balance)}.`);
      setBalance("");
      setReason("");
      const refreshed = await apiRequest<{ items: AdminMember[] }>(
        `/api/admin/members?query=${encodeURIComponent(search.trim())}`,
      );
      setMembers(refreshed.items);
      setSelected(refreshed.items.find((member) => member.id === selected.id) || null);
    } catch (requestError) {
      setError(errorText(requestError));
    } finally {
      setSaving(false);
    }
  }

  async function signOut() {
    if (!auth) return;
    setError("");
    try {
      await apiRequest("/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": auth.csrf_token },
      });
      setAuth(null);
      setDashboard(null);
      setTransactions(null);
      setOverview(null);
    } catch (requestError) {
      setError(errorText(requestError));
    }
  }

  if (busy) {
    return <main className="loading-screen"><span className="brand-mark">F</span><p>Loading your economy...</p></main>;
  }

  if (!auth || !dashboard) {
    return (
      <main className="login-screen">
        <div className="login-card">
          <span className="brand-mark">F</span>
          <p className="eyebrow">FIHCOIN ECONOMY</p>
          <h1>Your server.<br /><span>Your balance.</span></h1>
          <p className="muted">Sign in with Discord to see your Fihcoin profile, accounts, and transaction history.</p>
          {(loginMessage || error) && <div className="alert error">{loginMessage || error}</div>}
          <a className="button primary full" href={`${API_URL}/auth/login`}>Continue with Discord <span>↗</span></a>
          <p className="login-foot">Available to members of the configured Fihcoin server.</p>
        </div>
        <div className="login-orbit orbit-one" />
        <div className="login-orbit orbit-two" />
      </main>
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <a className="wordmark" href="#"><span className="brand-mark small">F</span><span>fihcoin<small>ECONOMY</small></span></a>
        <div className="nav-label">YOUR SPACE</div>
        <a className="nav-item active" href="#overview"><span className="nav-icon">◈</span> Overview</a>
        <a className="nav-item" href="#activity"><span className="nav-icon">↗</span> Transactions</a>
        {auth.is_admin && <><div className="nav-label admin-label">MANAGEMENT</div><a className="nav-item" href="#admin"><span className="nav-icon">⌘</span> Admin console</a></>}
        <div className="sidebar-bottom">
          <div className="server-chip"><span className="status-dot" /> Connected to your server</div>
          <button className="nav-item logout-button" onClick={() => void signOut()}><span className="nav-icon">↪</span> Sign out</button>
        </div>
      </aside>

      <section className="main-content">
        <header className="topbar">
          <div><p className="eyebrow">MEMBER DASHBOARD</p><h2>Overview</h2></div>
          <div className="user-chip">
            {dashboard.user.avatar_url ? <img src={dashboard.user.avatar_url} alt="" /> : <span className="avatar-fallback">{dashboard.user.name.slice(0, 1).toUpperCase()}</span>}
            <span><strong>{dashboard.user.name}</strong><small>#{dashboard.user.id}</small></span>
          </div>
        </header>

        {error && <div className="alert error page-alert">{error}</div>}
        {notice && <div className="alert success page-alert">{notice}</div>}

        <section id="overview" className="welcome-row">
          <div><p className="eyebrow">YOUR FIHCOIN PROFILE</p><h1>Good to see you, {dashboard.user.name.split(" ")[0]}.</h1><p className="muted">A clear view of your accounts and activity.</p></div>
          <div className="rank-pill"><span>♧</span><div><small>SERVER RANK</small><strong>#{dashboard.rank}</strong></div></div>
        </section>

        <section className="balance-grid">
          <article className="balance-card featured">
            <div className="card-top"><span className="balance-icon">◉</span><span className="card-caption">TOTAL BALANCE</span><span className="card-dot" /></div>
            <strong className="balance-amount">{money(dashboard.balances.total)}</strong>
            <div className="balance-foot"><span>Wallet + personal bank</span><span className="balance-symbol">FC</span></div>
          </article>
          <article className="balance-card">
            <div className="card-top"><span className="balance-icon wallet-icon">↗</span><span className="card-caption">WALLET</span></div>
            <strong className="balance-amount">{money(dashboard.balances.wallet)}</strong>
            <div className="balance-foot"><span>Ready to spend</span><span className="mini-line green" /></div>
          </article>
          <article className="balance-card">
            <div className="card-top"><span className="balance-icon bank-icon">▤</span><span className="card-caption">PERSONAL BANK</span></div>
            <strong className="balance-amount">{money(dashboard.balances.bank)}</strong>
            <div className="balance-foot"><span>Stored securely</span><span className="mini-line blue" /></div>
          </article>
        </section>

        <section className="details-grid">
          <article className="panel profile-panel">
            <div className="panel-heading"><div><p className="eyebrow">MEMBER PROFILE</p><h3>Your account</h3></div><span className="panel-symbol">◌</span></div>
            <div className="profile-details">
              <div><span>Discord account</span><strong>{dashboard.user.username}</strong></div>
              <div><span>Joined economy</span><strong>{date(dashboard.account_created_at)}</strong></div>
              <div><span>Transactions</span><strong>{dashboard.transaction_count.toLocaleString()}</strong></div>
              <div><span>Server rank</span><strong>#{dashboard.rank}</strong></div>
            </div>
          </article>
          <article className="panel activity-summary">
            <div className="panel-heading"><div><p className="eyebrow">ACTIVITY</p><h3>Economy snapshot</h3></div><span className="panel-symbol">⌁</span></div>
            <div className="snapshot-total">{dashboard.transaction_count.toLocaleString()}<span> total transactions</span></div>
            <p className="muted">Your balance is shared between your wallet and personal bank account.</p>
            <a className="text-link" href="#activity">View transaction history <span>→</span></a>
          </article>
        </section>

        <section id="activity" className="panel history-panel">
          <div className="panel-heading history-heading"><div><p className="eyebrow">LATEST ACTIVITY</p><h3>Transaction history</h3></div><span className="history-count">{transactions?.total ?? 0} records</span></div>
          {!transactions?.items.length ? <div className="empty-state"><span>◌</span><strong>No transactions yet</strong><p>Your economy activity will appear here.</p></div> : (
            <div className="table-scroll">
              <table><thead><tr><th>TRANSACTION</th><th>DETAIL</th><th>DATE</th><th className="align-right">AMOUNT</th></tr></thead>
                <tbody>{transactions.items.map((item) => {
                  const outgoing = item.sender_id === dashboard.user.id;
                  return <tr key={item.id}>
                    <td><span className={`transaction-type ${outgoing ? "outgoing" : "incoming"}`}>{outgoing ? "↗" : "↙"}</span><strong>{item.type.replaceAll("_", " ")}</strong></td>
                    <td className="transaction-note">{item.note || "—"}</td>
                    <td className="date-cell">{date(item.created_at)}</td>
                    <td className={`amount-cell ${outgoing ? "negative" : "positive"}`}>{outgoing ? "−" : "+"}{money(item.amount)}</td>
                  </tr>;
                })}</tbody>
              </table>
            </div>
          )}
          {transactions && transactions.total > transactions.limit && <div className="pagination"><button disabled={pageOffset === 0} onClick={() => void loadPage(Math.max(0, pageOffset - transactions.limit))}>← Newer</button><span>{pageOffset + 1}–{Math.min(pageOffset + transactions.items.length, transactions.total)} of {transactions.total}</span><button disabled={pageOffset + transactions.limit >= transactions.total} onClick={() => void loadPage(pageOffset + transactions.limit)}>Older →</button></div>}
        </section>

        {auth.is_admin && <section id="admin" className="admin-section">
          <div className="section-title"><div><p className="eyebrow">SERVER MANAGEMENT</p><h2>Admin console</h2></div><span className="admin-badge">ADMIN ACCESS</span></div>
          {overview && <div className="admin-stats">
            <article><span>REGISTERED MEMBERS</span><strong>{overview.members.toLocaleString()}</strong><small>Players with economy profiles</small></article>
            <article><span>TOTAL CIRCULATION</span><strong>{money(overview.circulation)}</strong><small>Wallets, personal banks, and shared vaults</small></article>
            <article><span>SHARED BANK VAULTS</span><strong>{money(overview.shared_bank_total)}</strong><small>Funds held in shared banks</small></article>
            <article><span>TRANSACTIONS · 24H</span><strong>{overview.transactions_24h.toLocaleString()}</strong><small>{money(overview.volume_24h)} transaction volume</small></article>
          </div>}
          <article className="panel lookup-panel">
            <div className="panel-heading"><div><p className="eyebrow">MEMBER TOOLS</p><h3>Member lookup</h3></div><span className="panel-symbol">⌕</span></div>
            <p className="muted">Search current server members by name or Discord ID. You can set an exact wallet or personal bank balance.</p>
            <form className="search-form" onSubmit={(event) => void searchMembers(event)}>
              <span>⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} minLength={2} placeholder="Search a name or Discord ID..." required /><button className="button primary" type="submit">Search</button>
            </form>
            {members.length > 0 && <div className="member-results">{members.map((member) => <button key={member.id} className={`member-row ${selected?.id === member.id ? "selected" : ""}`} onClick={() => { setSelected(member); setBalance(member.wallet); setAccountType("wallet"); }}>
              {member.avatar_url ? <img src={member.avatar_url} alt="" /> : <span className="avatar-fallback">{member.name.slice(0, 1).toUpperCase()}</span>}
              <span className="member-name"><strong>{member.name}</strong><small>{member.username} · {member.id}{member.has_profile ? "" : " · no economy profile"}</small></span>
              <span className="member-balance">{money(member.total)}<small>total balance</small></span>
              <span className="chevron">›</span>
            </button>)}</div>}
            {selected && <form className="balance-form" onSubmit={(event) => void setExactBalance(event)}>
              <div className="form-heading"><div><p className="eyebrow">SET EXACT BALANCE</p><h4>{selected.name}</h4></div><button className="icon-button" type="button" aria-label="Close member selection" onClick={() => setSelected(null)}>×</button></div>
              <div className="form-grid">
                <label>Account<select value={accountType} onChange={(event) => {
                  const selectedType = event.target.value as "wallet" | "bank";
                  setAccountType(selectedType);
                  setBalance(selectedType === "wallet" ? selected.wallet : selected.bank);
                }}><option value="wallet">Wallet</option><option value="bank">Personal bank</option></select></label>
                <label>New balance <span className="input-suffix">FC</span><input type="number" min="0" max="999999999999999999.99" step="0.01" value={balance} onChange={(event) => setBalance(event.target.value)} required /></label>
              </div>
              <label>Reason for this adjustment<input value={reason} onChange={(event) => setReason(event.target.value)} minLength={1} maxLength={500} placeholder="Required for the audit log" required /></label>
              <div className="form-actions"><span>Previous: {money(accountType === "wallet" ? selected.wallet : selected.bank)}</span><button className="button primary" type="submit" disabled={saving}>{saving ? "Saving..." : "Set balance"}</button></div>
            </form>}
          </article>
        </section>}
        <footer className="page-footer"><span>FIHCOIN ECONOMY</span><span>Balances and history update from the live server economy.</span></footer>
      </section>
    </main>
  );
}
