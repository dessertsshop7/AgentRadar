import HealthPanel from "./health-panel";

export default function Page() {
  return (
    <main>
      <header>
        <p className="eyebrow">AgentRadar / P00</p>
        <h1>工程健康检查</h1>
        <p className="intro">验证前端、后端与数据库的真实连接。状态来自最近一次检查。</p>
      </header>
      <HealthPanel />
    </main>
  );
}
