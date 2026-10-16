import type { Metadata } from "next";
import HealthPanel from "../health-panel";

export const metadata: Metadata = { title: "工程状态" };

export default function StatusPage() {
  return (
    <main className="page-container status-page" id="main-content" tabIndex={-1}>
      <header>
        <p className="eyebrow">AgentRadar / 工程基础</p>
        <h1>工程健康检查</h1>
        <p className="intro">验证前端、后端与数据库的真实连接。状态来自最近一次检查。</p>
      </header>
      <HealthPanel />
    </main>
  );
}
