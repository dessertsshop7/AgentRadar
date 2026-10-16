import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import DemoNotice from "../../../components/demo-notice";
import { difficultyLabels } from "../../../lib/catalog-types";
import { getDemoCategoryLabel, getDemoTool } from "../../../lib/demo-catalog";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  return { title: getDemoTool(slug)?.name ?? "工具未找到" };
}

export default async function ToolPage({ params }: Props) {
  const { slug } = await params;
  const tool = getDemoTool(slug);
  if (!tool) notFound();
  return (
    <main className="page-container" id="main-content" tabIndex={-1}>
      <DemoNotice />
      <nav className="breadcrumb" aria-label="当前位置"><Link href="/discover">← 返回发现页</Link><span>/</span><span>工具详情</span></nav>
      <header className="tool-heading">
        <span className="tool-mark tool-mark-large" aria-hidden="true">{tool.mark}</span>
        <div><div className="tags"><span className="badge">{tool.kind}</span><span className="badge">{getDemoCategoryLabel(tool.category)}</span><span className="badge">{difficultyLabels[tool.difficulty]}</span></div>
          <h1>{tool.name}</h1><p className="intro">{tool.summary}</p>
        </div>
      </header>
      <div className="detail-layout">
        <div className="detail-content">
          <section className="content-panel"><p className="eyebrow">01 / 理解用途</p><h2>它可以帮助你做什么</h2>
            <p>{tool.description}</p><ul className="readable-list">{tool.capabilities.map((item) => <li key={item}>{item}</li>)}</ul>
          </section>
          <section className="content-panel"><p className="eyebrow">02 / 判断适配</p><h2>适合与不适合</h2>
            <div className="fit-grid"><div className="fit-box"><h3>可以考虑</h3><ul>{tool.fits.map((item) => <li key={item}>{item}</li>)}</ul></div>
              <div className="fit-box fit-caution"><h3>先别急着选择</h3><ul>{tool.not_for.map((item) => <li key={item}>{item}</li>)}</ul></div></div>
          </section>
          <section className="content-panel"><p className="eyebrow">03 / 确认条件</p><h2>试用前先检查</h2>
            <ul className="readable-list">{tool.requirements.map((item) => <li key={item}>{item}</li>)}</ul>
            <h3>仍需核实的限制</h3><ul className="readable-list">{tool.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            <div className="note"><strong>这是概念性检查清单。</strong> 本案例没有实际软件可安装，也没有运行结果。</div>
          </section>
          <section className="content-panel"><h2>来源与可信边界</h2><p>{tool.source_note}</p>
            <dl className="source-details"><div><dt>内容类型</dt><dd>虚构产品概念</dd></div><div><dt>核验情况</dt><dd>未采集、未安装验证、未调用模型</dd></div></dl>
            <p className="small muted">真实版本需要展示官方仓库、资料定位和实际核对时间。本案例不提供对应的外链。</p>
          </section>
        </div>
        <aside className="decision-aside" aria-label="下一步决策">
          <div className="decision-card"><p className="eyebrow">从了解，走向判断</p><h2>把工具放回你的任务里</h2>
            <p>工具看起来合适，还要确认技术条件和你愿意投入的精力。</p>
            <Link className="button" href={`/assistant?tool=${tool.slug}`}>用这个场景试试选型助手</Link>
            <p className="small">演示交互，未连接模型。</p>
          </div>
          <div className="content-panel compact-panel"><h3>先做一次小范围判断</h3><ol className="readable-list">{tool.first_steps.map((item) => <li key={item}>{item}</li>)}</ol>
            <p className="small muted">正式试用与结果反馈功能规划中。</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
