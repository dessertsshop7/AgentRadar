import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "AgentRadar · 工程验证" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
