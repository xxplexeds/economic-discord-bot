import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Fihcoin Dashboard",
  description: "Your Fihcoin economy profile and account activity.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
