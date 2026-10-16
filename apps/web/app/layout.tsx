import type { Metadata } from "next";
import SiteHeader from "../components/site-header";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "AgentRadar · 从发现到应用", template: "%s · AgentRadar" },
  description: "AgentRadar P01 产品原型：发现工具、理解用途与限制、体验固定选型演示。",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main-content">跳到主要内容</a>
        <SiteHeader />
        {children}
        <footer className="site-footer"><span translate="no">AgentRadar</span><p>P01 产品原型 · 先理解，再尝试。当前未提供真实工具推荐、安装或结果追踪。</p></footer>
      </body>
    </html>
  );
}
