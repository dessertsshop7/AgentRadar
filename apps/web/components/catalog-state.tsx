import type { CatalogState as State } from "../lib/catalog-types";

export default function CatalogState({ phase, retry }: { phase: State["phase"]; retry: () => void }) {
  if (phase === "loading") {
    return (
      <div className="state-panel" data-catalog-state="loading" aria-busy="true">
        <p className="eyebrow">准备目录</p>
        <p role="status">正在读取演示目录…</p>
        <div className="skeleton-lines" aria-hidden="true"><span /><span /><span /></div>
      </div>
    );
  }
  if (phase === "error") {
    return (
      <div className="state-panel state-error" role="alert">
        <h2>演示目录读取失败</h2>
        <p>请检查网络后重试。这不代表后端或数据库异常，可到工程状态页单独检查。</p>
        <button className="button button-secondary" type="button" onClick={retry}>重试读取</button>
      </div>
    );
  }
  return (
    <div className="state-panel">
      <h2>演示目录暂时没有内容</h2>
      <p>目录文件已读取，但还没有可展示的案例。可以稍后重试。</p>
      <button className="button button-secondary" type="button" onClick={retry}>重试读取</button>
    </div>
  );
}
