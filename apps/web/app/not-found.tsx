import Link from "next/link";

export default function NotFound() {
  return (
    <main className="page-container" id="main-content" tabIndex={-1}>
      <div className="state-panel"><p className="eyebrow">未找到 / NOT FOUND</p><h1>没有找到这个页面或演示工具</h1>
        <p>地址可能不存在，或对应功能仍在规划中。可以从已开放的目录继续。</p>
        <Link href="/discover" className="button">返回发现页</Link>
      </div>
    </main>
  );
}
