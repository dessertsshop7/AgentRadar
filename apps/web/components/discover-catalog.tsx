"use client";

import Form from "next/form";
import Link from "next/link";
import { difficultyLabels } from "../lib/catalog-types";
import { useDemoCatalog } from "../lib/use-demo-catalog";
import CatalogState from "./catalog-state";
import ToolCard from "./tool-card";

export type DiscoverFilters = { query: string; category: string; level: string };

export default function DiscoverCatalog({ filters }: { filters: DiscoverFilters }) {
  const { state, retry } = useDemoCatalog();
  if (state.phase !== "ready") return <CatalogState phase={state.phase} retry={retry} />;
  const { catalog } = state;
  if (catalog.tools.length === 0) return <CatalogState phase="ready" retry={retry} />;

  const validFilters = (!filters.category || catalog.categories.some((item) => item.id === filters.category)) &&
    (!filters.level || Object.hasOwn(difficultyLabels, filters.level));
  const query = filters.query.trim().normalize("NFKC").toLowerCase();
  const tools = validFilters ? catalog.tools.filter((tool) => {
    const category = catalog.categories.find((item) => item.id === tool.category)?.label ?? "";
    const searchable = [tool.name, tool.slug, tool.summary, category, ...tool.tags].join(" ").normalize("NFKC").toLowerCase();
    return (!query || searchable.includes(query)) &&
      (!filters.category || tool.category === filters.category) &&
      (!filters.level || tool.difficulty === filters.level);
  }) : [];

  return (
    <Form action="/discover" className="discovery-form">
      <div className="search-bar">
        <div className="search-field">
          <label htmlFor="tool-search">搜索工具</label>
          <input id="tool-search" type="search" name="q" defaultValue={filters.query} maxLength={100}
            autoComplete="off" placeholder="试试“知识库”“文档整理”或 MCP…" />
        </div>
        <button className="button" type="submit">搜索与筛选 <span aria-hidden="true">→</span></button>
      </div>
      <div className="catalog-layout">
        <aside className="filter-panel" aria-label="目录筛选">
          <div className="section-topline"><h2>缩小范围</h2><span className="small muted">按你的条件</span></div>
          <div className="field">
            <label htmlFor="category">应用场景</label>
            <select id="category" name="category" defaultValue={filters.category}>
              <option value="">全部场景</option>
              {catalog.categories.map((category) => <option key={category.id} value={category.id}>{category.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="level">上手门槛</label>
            <select id="level" name="level" defaultValue={filters.level}>
              <option value="">全部门槛</option>
              {Object.entries(difficultyLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <button className="button button-secondary filter-apply" type="submit">应用筛选</button>
          <p className="small muted">先选场景和门槛，再应用筛选。这里没有按热度推断适配。</p>
          <div className="filter-tip"><span className="eyebrow">选型小提示</span><p>先看能解决什么，<br />再确认你能否用起来。</p></div>
        </aside>
        <section aria-labelledby="results-heading" className="catalog-results">
          <div className="results-heading">
            <div><p className="eyebrow">按场景探索</p><h2 id="results-heading">工具目录 <span className="result-count">{tools.length} 条演示条目</span></h2></div>
            <span className="small muted">演示顺序 · 非实时排行</span>
          </div>
          <p className="sr-only" role="status">找到 {tools.length} 条演示条目。</p>
          {!validFilters ? <p className="inline-error" role="alert">筛选条件无效，请清除筛选后重新选择。</p> : null}
          {tools.length ? (
            <div className="tool-grid">
              {tools.map((tool) => <ToolCard key={tool.slug} tool={tool}
                category={catalog.categories.find((category) => category.id === tool.category)?.label ?? tool.category} />)}
            </div>
          ) : (
            <div className="state-panel"><h3>没有找到匹配的演示工具</h3><p>试试更短的关键词，或减少场景和门槛限制。</p>
              <Link className="button button-secondary" href="/discover">清除筛选</Link>
            </div>
          )}
        </section>
      </div>
    </Form>
  );
}
