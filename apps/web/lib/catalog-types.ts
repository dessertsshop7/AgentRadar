export type DemoTool = {
  slug: string;
  name: string;
  mark: string;
  kind: string;
  category: string;
  difficulty: string;
  summary: string;
  description: string;
  tags: string[];
  capabilities: string[];
  fits: string[];
  not_for: string[];
  requirements: string[];
  limitations: string[];
  first_steps: string[];
  source_note: string;
};

export type DemoCatalog = {
  schema_version: number;
  provenance: string;
  categories: { id: string; label: string; description: string }[];
  tools: DemoTool[];
};

export const difficultyLabels: Record<string, string> = {
  beginner: "无需代码（示例设定）",
  visual: "可视化配置",
  developer: "需要开发支持",
};

export type CatalogState =
  | { phase: "loading" }
  | { phase: "error" }
  | { phase: "ready"; catalog: DemoCatalog };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

// 静态文件同样可能下载失败或格式损坏；只验证当前页面实际需要的字段。
export function isDemoCatalog(value: unknown): value is DemoCatalog {
  if (!isRecord(value) || value.schema_version !== 1 || value.provenance !== "fictional-demo") return false;
  if (!Array.isArray(value.categories) || !Array.isArray(value.tools)) return false;
  const strings = ["slug", "name", "mark", "kind", "category", "difficulty", "summary", "description", "source_note"];
  const lists = ["tags", "capabilities", "fits", "not_for", "requirements", "limitations", "first_steps"];
  return value.categories.every((item) => isRecord(item) &&
    ["id", "label", "description"].every((key) => typeof item[key] === "string")) &&
    value.tools.every((tool) => isRecord(tool) &&
      strings.every((key) => typeof tool[key] === "string") &&
      lists.every((key) => Array.isArray(tool[key]) && tool[key].every((item: unknown) => typeof item === "string")));
}
