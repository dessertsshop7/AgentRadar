# P02 查询接口与 P03 输入

2026-10-18。基础地址：浏览器/宿主机 `http://localhost:8000`；容器内 `http://api:8000`。
API 前缀 `/api/v1`，在线 OpenAPI 位于 `/api/v1/docs`。查询不会触发采集或模型调用。

| 方法/路径 | 参数与返回 | 可见性 |
| --- | --- | --- |
| GET /assets | q ≤100 字；category 四类词表；difficulty 四类枚举；kind 五类资产类型；maintenance 四类维护状态；page 1–10000；page_size 1–50；sort=slug 或 updated | 已审内容；默认 slug 升序，updated 按主仓库 pushed_at 降序，未知值最后，再按 slug |
| GET /assets/{id} | UUID 或稳定 slug；返回 item、request_id | 不存在/草稿/撤下/来源待核实统一 404 |
| GET /categories | items 中包含 id、label、count；request_id | 只统计已发布版本中的分类，零公开条目时返回空数组 |
| GET /trending | page、page_size 同列表，支持 category/kind/maintenance；分数降序、slug 平局排序 | 已发布且有真实主仓库观测；无足够增长信息时明确 null |
| GET /health | 保留 P00 真实 SQL 健康状态 | 数据库失败 503，不替换成静态状态 |

列表统一字段为 items、total、page、page_size、request_id；详情为 item、request_id。
item 包含 id、slug、name、kind、summary_zh、description_zh、difficulty、cost、tags、scenarios、
requirements、limitations、categories、content_version_id、source_hash、origin、review、needs_review、
collected_at、sources。趋势项额外有 trend（版本、分项、得分、实际窗口、样本数、growth_known、star_growth）。
sources 给出可核实 URL、来源 ID、采集时间和未知许可证；不会返回整份 raw_data 或令牌。

2026-10-29 缺陷修复新增契约：

- `kind`：tool / agent / skill / mcp / framework；所有筛选按 AND 合并，非法枚举返回 422。
- `maintenance`：active（主仓库 180 天内 push）、inactive（超过 180 天）、unknown（无主仓库或 push 未知）、needs_review（来源已变化）。needs_review 优先于活跃判断；当前因来源不可用隐藏的资产仍不会进入任何筛选。
- item 新增 `source_updated_at`（主仓库 push）、`content_updated_at`（中文版本创建时间）、`maintenance`。采集时间仍单列 collected_at，不能当成内容更新或数据过期的证明。
- GitHub sources 新增 pushed_at、stars、archived、availability；未关联仓库的 Registry 条目维护状态可以为 unknown。P03 可根据 collected_at 和自己的过期阈值显示数据新鲜度，不把它等同于维护状态。
- 列表、详情、分类和趋势现在统一设置 30 秒公开缓存。

2026-10-28 补充：`review` 包含 `actor_type`、`reviewed_by`、`reviewed_at`。
新人工审核为 `human`，用户明确委托的 AI 审核为 `delegated_ai`，缺少历史类型记录时为 `unknown`。
`origin=assistant_draft` 表示中文内容由助手整理，发布后仍保留，不等于“尚未审核”。
本轮 103 项真实发布内容均为 `assistant_draft` + `delegated_ai` + `reviewed_by=ai:codex`，不是人类审批或安装成功证明。

## 查询约定

中文使用真实 PostgreSQL 参数化 ILIKE，q 去除首尾空白后按**完整连续子串**匹配名称、已审摘要、说明、
标签和场景；ASCII 忽略大小写。不是中文分词、同义词或语义搜索，多个词不会自动拆成 OR。
反斜杠、% 和 _ 按字面量处理，不开放任意 SQL 通配符；q 与分类/门槛按 AND 组合。
无结果为 HTTP 200 + 空 items，非法参数为 422 + VALIDATION_ERROR。
数据库不可用的目录查询为 503 + HTTP_503，健康接口保留 DATABASE_UNAVAILABLE；未知详情为 HTTP_404。
所有错误复用 error.code、error.message、request_id，并有 X-Request-ID 响应头关联日志。

列表/详情缓存上限 30 秒；health 不缓存。缓存中的条目可能在撤下后短暂保留，当前不提供实时撤回机制。
CORS 沿用明确的 localhost 来源和 GET/X-Request-ID；P02 没有 HTTP 写接口，因此未扩大允许方法。
维护写操作只能通过具备本机/容器及数据库访问权的 CLI 执行。

## P03 接入约束

- 只维护 assets 一套 API，不新增重复 tools 接口。`/tools/[slug]` 可直接以 slug 请求详情。
- 当前 P01 的 knowledge/operations/support 是演示分类，不能直接套用到真实四类词表；应读取 categories。
- URL level 显式转换为 difficulty；beginner/visual/developer 同名，新增 unknown 要有“待核实”显示。
- P01 的 kind 为展示文案；真实 kind 是资产类型代码，需做中文显示映射。
- 使用实际分页，处理加载、空结果、503、404、unknown 及 needs_review；不能因为公开池为空而读演示文件冒充真实目录。
- 公开池只包含完成受控审核的版本；前端须展示审核类型与内容来源。本轮为明确委托的 AI 资料审核，不能显示成人工认证。
- P02 未实现 `/discover`、`/tools`、`/assistant` 的真实数据接入，也没有开放趋势页面。
- 不将外链点击作为安装成功，不把 MCP Registry 登记当作实际运行/安全验证。

本轮中文检索证据位于 `artifacts/p02/chinese-search.json`（Git 忽略）：真实 PostgreSQL、合成已审夹具、
中文命中/空结果/标签/字面量符号与实际 HTTP 耗时。它证明数据库查询行为，不代表真实发布内容的用户召回率。
当前规模未引入搜索索引或中文分词；ILIKE 包含匹配可能顺序扫描，扩量后需实测延迟与召回再决定索引。
2026-10-28 已在 103 项真实公开内容上再次验证：知识库命中 8、工作流命中 25、数据库命中 7、未知词命中 0。
当前证据为 `artifacts/p02/delegated-review-20261028/verification.json`；这些计数只证明当时内容的子串匹配结果，不代表用户召回率。
