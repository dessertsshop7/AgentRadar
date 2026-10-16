import type { Metadata } from "next";
import Link from "next/link";
import DemoNotice from "../../components/demo-notice";
import DiscoverCatalog from "../../components/discover-catalog";

export const metadata: Metadata = { title: "发现工具" };

export default async function DiscoverPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const filters = {
    query: typeof params.q === "string" ? params.q.slice(0, 100) : "",
    category: typeof params.category === "string" ? params.category : "",
    level: typeof params.level === "string" ? params.level : "",
  };
  return (
    <main className="page-container" id="main-content" tabIndex={-1}>
      <DemoNotice />
      <section className="discovery-intro" aria-labelledby="discovery-title">
        <div><p className="eyebrow">从工作任务出发 / DISCOVER</p><h1 id="discovery-title">找到值得一试的 AI 工具</h1>
          <p className="intro">先看懂用途与限制，再判断它是否适合你的工作。</p>
          <div className="intro-steps" aria-label="产品任务路径"><span>发现工具</span><span aria-hidden="true">→</span><span>理解与判断</span><span aria-hidden="true">→</span><span>有准备地尝试</span></div>
        </div>
        <div className="intro-aside"><span className="eyebrow">已有具体问题？</span><p>把任务和条件说清楚，<br />看看选型过程如何展开。</p>
          <Link href="/assistant" className="text-link">试试选型助手 <span aria-hidden="true">↗</span></Link>
        </div>
      </section>
      <DiscoverCatalog key={JSON.stringify(filters)} filters={filters} />
    </main>
  );
}
