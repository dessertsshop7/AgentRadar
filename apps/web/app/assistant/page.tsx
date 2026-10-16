import type { Metadata } from "next";
import AssistantPanel from "../../components/assistant-panel";
import DemoNotice from "../../components/demo-notice";
import { getDemoTool } from "../../lib/demo-catalog";

export const metadata: Metadata = { title: "选型助手 · 演示" };

export default async function AssistantPage({ searchParams }: {
  searchParams: Promise<{ tool?: string | string[] }>;
}) {
  const { tool } = await searchParams;
  const selected = typeof tool === "string" ? getDemoTool(tool) : undefined;
  const contextTool = selected ? { slug: selected.slug, name: selected.name, category: selected.category } : null;
  return (
    <main className="page-container" id="main-content" tabIndex={-1}>
      <DemoNotice />
      <header className="page-heading"><p className="eyebrow">从任务到候选 / ASSISTANT</p><h1>选工具，先把需求说清楚</h1>
        <p className="intro">用一个固定演示，看看如何把工作任务、技术条件和候选工具放在一起判断。</p>
      </header>
      <AssistantPanel key={typeof tool === "string" ? tool : "default"} contextTool={contextTool} unknownContext={Boolean(tool && !selected)} />
    </main>
  );
}
