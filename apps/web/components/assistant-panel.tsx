"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { difficultyLabels, type DemoTool } from "../lib/catalog-types";
import { useDemoCatalog } from "../lib/use-demo-catalog";
import CatalogState from "./catalog-state";

type ToolContext = Pick<DemoTool, "slug" | "name" | "category">;
type DemoResult = { need: string; scenario: string; technical: string; tool: DemoTool };

// 只按两个显式选项映射虚构案例，不读取文本含义，不进行真实推荐。
const fixedRules: Record<string, Record<string, string>> = {
  knowledge: { beginner: "knowledge-base", developer: "document-parser" },
  operations: { beginner: "content-planner", developer: "workflow-builder" },
  support: { beginner: "ticket-triage", developer: "data-connector" },
};

export default function AssistantPanel({ contextTool, unknownContext }: {
  contextTool: ToolContext | null;
  unknownContext: boolean;
}) {
  const { state, retry } = useDemoCatalog();
  const [result, setResult] = useState<DemoResult | null>(null);
  const [error, setError] = useState("");
  const needRef = useRef<HTMLTextAreaElement>(null);
  const resultRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (result) resultRef.current?.focus();
  }, [result]);

  if (state.phase !== "ready") return <CatalogState phase={state.phase} retry={retry} />;
  const { catalog } = state;
  if (catalog.tools.length === 0) return <CatalogState phase="ready" retry={retry} />;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // 校验失败时不继续展示上次提交的方案，避免把旧结果当作本次结果。
    setResult(null);
    const form = new FormData(event.currentTarget);
    const need = String(form.get("need") ?? "").trim();
    if (need.replace(/\s/g, "").length < 10 || need.length > 500) {
      setError("请至少输入 10 个非空白字符，并控制在 500 字以内，说明你要完成的具体任务。");
      needRef.current?.focus();
      return;
    }
    const scenario = String(form.get("scenario") ?? "");
    const technical = String(form.get("technical") ?? "");
    const rule = Object.hasOwn(fixedRules, scenario) ? fixedRules[scenario] : undefined;
    const slug = rule && Object.hasOwn(rule, technical) ? rule[technical] : undefined;
    const tool = catalog.tools.find((item) => item.slug === slug);
    if (!tool) {
      setError("当前条件没有对应的演示案例，请重新选择场景和技术条件。");
      return;
    }
    setError("");
    setResult({ need, scenario, technical, tool });
  }

  const scenarioLabel = result ? catalog.categories.find((item) => item.id === result.scenario)?.label : "";
  const technicalLabel = result?.technical === "developer" ? "有开发支持" : "不能写代码";

  return (
    <div className="assistant-layout">
      <div className="assistant-main">
        {contextTool ? <div className="tool-context"><p>正在评估：{contextTool.name}</p><Link href={`/tools/${contextTool.slug}`}>查看这个案例</Link></div> : null}
        {unknownContext ? <p className="note">没有找到带入的演示工具，请重新选择业务场景。</p> : null}
        <form className="content-panel assistant-form" onSubmit={submit} noValidate data-testid="assistant-form">
          <p className="eyebrow">01 / 描述你的任务</p><h2>先说说，你想完成什么</h2>
          <div className="field"><label htmlFor="need">你想解决什么问题</label>
            <p id="need-hint" className="field-hint">写清楚任务、已有资料和想得到的结果。10–500 字，不要输入密钥或个人敏感信息。</p>
            <textarea ref={needRef} id="need" name="need" rows={5} maxLength={500} autoComplete="off" required
              placeholder="例如：把团队文档整理成知识库，让同事能查询流程，并核对答案出处…"
              aria-invalid={error ? true : undefined} aria-describedby={error ? "need-hint need-error" : "need-hint"} />
            {error ? <p className="inline-error" id="need-error" role="alert">{error}</p> : null}
          </div>
          <div className="form-columns"><div className="field"><label htmlFor="scenario">业务场景</label>
            <select id="scenario" name="scenario" defaultValue={contextTool?.category ?? "knowledge"}>
              {catalog.categories.map((category) => <option value={category.id} key={category.id}>{category.label}</option>)}
            </select></div>
            <div className="field"><label htmlFor="technical">技术条件</label><select id="technical" name="technical" defaultValue="beginner">
              <option value="beginner">不能写代码</option><option value="developer">有开发支持</option>
            </select></div>
          </div>
          <div className="note"><strong>演示交互，未连接模型。</strong> 固定规则仅使用所选场景和技术条件，输入文本不参与语义分析。</div>
          <button className="button" type="submit">展示演示方案 <span aria-hidden="true">→</span></button>
          <p className="small muted form-privacy">演示输入只保留在当前页面内存中，离开或刷新即清除；不会保存或提交到业务服务。</p>
        </form>
        {result ? (
          <section className="content-panel assistant-result" data-testid="assistant-result" aria-labelledby="result-title">
            <p className="eyebrow">02 / 理解候选与限制</p><h2 id="result-title" ref={resultRef} tabIndex={-1}>你的演示选型方案</h2>
            <p className="badge badge-demo">演示交互，未连接模型</p>
            <p className="result-reason"><strong>固定规则：</strong>你选择了“{scenarioLabel}”与“{technicalLabel}”，因此展示这个虚构案例。</p>
            <p className="small muted">输入文本不参与语义分析；相同选项始终展示相同案例，不代表已经理解需求或完成真实推荐。</p>
            <div className="candidate"><span className="tool-mark" aria-hidden="true">{result.tool.mark}</span><div><p className="small muted">候选案例 / {difficultyLabels[result.tool.difficulty]}</p>
              <h3><Link href={`/tools/${result.tool.slug}`}>{result.tool.name}</Link></h3><p>{result.tool.summary}</p></div></div>
            <h3>你提供的任务</h3><p className="need-quote">{result.need}</p>
            <h3>还需要你判断</h3><ul className="readable-list">{result.tool.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            {result.technical === "beginner" && result.tool.difficulty !== "beginner" ? <p className="note">你选择了不能写代码，但该案例仍需可视化配置。先确认是否有人协助，不能直接视为满足条件。</p> : null}
            <h3>下一步，做一次小范围检查</h3><ol className="readable-list">{result.tool.first_steps.map((item) => <li key={item}>{item}</li>)}</ol>
            <div className="actions"><Link className="button" href={`/tools/${result.tool.slug}`}>查看候选详情</Link>
              <button className="button button-secondary" type="button" onClick={() => { setResult(null); needRef.current?.focus(); }}>修改需求</button></div>
            <p className="small muted">试用与结果反馈 · 规划中。这里没有实际安装或成功应用记录。</p>
          </section>
        ) : null}
      </div>
      <aside className="assistant-aside"><div className="content-panel compact-panel"><p className="eyebrow">一次选择，三个问题</p>
        <ol className="decision-steps"><li><span>01</span><div><h3>任务是什么</h3><p>描述要完成的工作，而不只是想用 AI。</p></div></li><li><span>02</span><div><h3>条件是否满足</h3><p>确认配置门槛、资料权限和未知费用。</p></div></li><li><span>03</span><div><h3>怎样判断有效</h3><p>先准备小样本和人工核对标准。</p></div></li></ol>
        <div className="note small">演示只展示选型过程。真实推荐、模型调用和结果追踪尚未实现。</div>
      </div></aside>
    </div>
  );
}
