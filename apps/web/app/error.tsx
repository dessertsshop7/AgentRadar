"use client";

import Link from "next/link";

export default function ErrorPage({ retry }: { error: unknown; retry: () => void }) {
  return (
    <main className="page-container" id="main-content" tabIndex={-1}>
      <div className="state-panel state-error" role="alert"><h1>页面暂时无法显示</h1>
        <p>请重新加载，或返回发现页继续浏览。</p>
        <div className="actions"><button className="button" type="button" onClick={retry}>重新加载页面</button>
          <Link href="/discover" className="button button-secondary">返回发现页</Link></div>
      </div>
    </main>
  );
}
