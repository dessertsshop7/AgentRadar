import Link from "next/link";
import { difficultyLabels, type DemoTool } from "../lib/catalog-types";

export default function ToolCard({ tool, category }: { tool: DemoTool; category: string }) {
  return (
    <article className="tool-card" data-testid="tool-card">
      <div className="card-topline">
        <span className="tool-mark" aria-hidden="true">{tool.mark}</span>
        <span className="badge">{tool.kind}</span>
      </div>
      <h3><Link href={`/tools/${tool.slug}`}>{tool.name}</Link></h3>
      <p className="card-summary">{tool.summary}</p>
      <div className="tags" aria-label="工具标签">
        {tool.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
      </div>
      <div className="card-meta">
        <span>{category}</span><span>{difficultyLabels[tool.difficulty] ?? "门槛待核实"}</span>
      </div>
      <Link className="card-source" href={`/tools/${tool.slug}`} aria-label={`查看${tool.name}的用途与限制`}>
        虚构案例 · 查看用途与限制 <span aria-hidden="true">→</span>
      </Link>
    </article>
  );
}
