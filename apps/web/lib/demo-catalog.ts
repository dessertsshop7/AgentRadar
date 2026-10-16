import data from "../public/demo/catalog.json";
import type { DemoCatalog } from "./catalog-types";

// 详情的服务端读取入口，与客户端静态请求共用唯一的数据文件。P02 在此接真实目录。
const catalog: DemoCatalog = data;

export function getDemoTool(slug: string) {
  return catalog.tools.find((tool) => tool.slug === slug);
}

export function getDemoCategoryLabel(id: string) {
  return catalog.categories.find((category) => category.id === id)?.label ?? id;
}
