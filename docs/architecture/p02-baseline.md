# P02 真实采集与资产中心交付基线

日期：2026-10-18（Asia/Singapore）。依据 V2.0、仍有效的 V1.1、用户附件 P02 Prompt。
**以下保留 10 月 18 日工程与采集的历史结果，当时人工发布池尚未达标。**
2026-10-28 更新：用户明确委托 AI 代审后，已发布 103 项、暂缓 30 项，四类各≥20；
当前结果、补充测试和真实数据核验见 [委托审核执行报告](../operations/p02-delegated-review-20261028.md)。
该委托不等于人类逐条审核或 P02 阶段验收；尚未提交 Git，未进入 P03。
2026-10-29 后续状态：按用户“达标后提交推送”指令完成 [验收复核](../operations/p02-acceptance-20261029.md)，
当前满足 P02 要求；以下数字与检查仍保留其历史日期。

## 衔接与取舍

开始时 main 为已验收 P01 提交 dae1a5b；工作区已有用户修改的 AGENTS.md，继续保留并增补，没有重置历史。
P00 配置、异步会话、错误/请求 ID/日志、Compose、CI 和 P01 页面/静态演示/测试复用。
先核查令牌与 Docker，实际读到本机新保存的 GITHUB_TOKEN 后，GitHub 认证和真实搜索返回 200，才开始实现。
真实凭据未输出、未修改；本机运行环境 Git 2.55、Python 3.12、Node 24、Docker Engine 29.8 可用。

P01 原 Tool 草案由 Repository/Asset 分离的真实契约取代，不额外维护 tools API。
前端仍是六条明确标注的虚构案例；/status 的真实 SQL 状态与 P00 API 契约保留。
维护使用本机/容器 CLI 权限与数据库凭据，不增加后台、匿名写 HTTP、身份系统、LLM、向量检索或企业功能。
httpx 从开发依赖进入生产依赖；新增 APScheduler 3.11.3 和 tzlocal 传递依赖；既有锁定版本未做无关升级。

## 架构、目录与请求链

```text
公开 GET /api/v1/assets、详情、categories、trending
  → FastAPI 参数/统一错误/请求 ID → 只读已审版本查询 → PostgreSQL

受控 CLI 或显式开启的调度器
  → 来源任务/数据库 advisory lock → 官方 Adapter（有界 HTTP）
  → 原始元数据/README 证据/待审版本/真实快照 → 人工起草与审核 → 发布指针

P01 页面 → 集中静态演示 JSON；/status → 原真实 health → SELECT 1
```

- app/db/models.py：九种核心实体和三张必要关联/证据/得分表，详见 [数据字典](p02-data-dictionary.md)。
- app/ingestion/providers.py：官方请求、可信重定向、解压后大小边界、超时/重试/配额、分页。
- app/ingestion/sync.py：短数据事务、整来源锁、幂等、MCP 批次检查点、失败和中断恢复。
- app/ingestion/rules.py：规则分类、可解释趋势、可信目录只读 Skill 元信息。
- app/ingestion/maintenance.py + app/cli.py：草稿、明确人工发布、撤下和审核队列；不会自动签署人类审核。
- app/ingestion/scheduler.py：默认关闭，启动/tick 检查，过期只补跑一次，无历史日程回放。
- app/api/assets.py：分页、筛选、中文子串查询与四类公开读取；[API 契约](../api/p02-assets.md)。
- 新增 0002_p02_assets 和 0003_p02_review；未修改 P00 基线。0003 用于当前来源指针和已审分类隔离，
  没有回改已经执行过的 0002。独立测试库实际完成升级、降至 P00、再升级及迁移 head 校验。
- 配置仅在后端，GITHUB_TOKEN 不进入前端、迁移容器或镜像；默认 SYNC_ENABLED=false。
  新增 HTTP 写方法为零，CORS 继续明确限制 GET/X-Request-ID。

## 真实数据验收

以下为 **2026-10-18 07:03:35 +08:00** 对开发数据库的实际查询，不是目标值或替身结果：

| 项目 | 实际值 | 验收解释 |
| --- | --- | --- |
| 去重 GitHub 仓库 | 1257，distinct 官方 ID 同为 1257 | 达到采集池≥1000；真实公开元数据 |
| MCP Registry 资产 | 103 | 来自官方 v0.1；游标续跑，尚未扫描完整目录 |
| 资产总数 | 1360 | Github 和 MCP 独立身份；不按同名合并 |
| 具有 README 的仓库 | 123 / 1257，约 9.79% | 单独报告覆盖，不声称全部已读文档 |
| 精确 180 天内且未归档 | 1255 | 另两条位于 Search 日期边界，精确时间门槛已过且无 README；仍在待审池，不可直接发布 |
| 真实指标快照 | 1387 | 同一任务不重复；跨主题任务的真实再观测保留 |
| 全部资产审核状态 | 1360 pending | 没有把助手或登记内容冒充人工审核 |
| 已审内容/公开资产 | 0 / 0 | 发布≥100及四类各≥20 **未达标** |

规则候选场景可重叠：知识管理/RAG 497、Agent/工作流 829、MCP/集成 727、开发框架 213。
有 README 的首批 123 个不同候选中，对应分类命中为 45、82、58、45；这只是待审分类，**不是已发布分布**。
真实快照的整个窗口仅为本地 06:51:49–06:56:56，不能用作过去七天增长的证据。

真实来源计划范围：三仓库小样本；rag、ai-agent、mcp、llm-framework 的近期/Stars 查询；MCP 首批三条及后续100条。
前面三类 GitHub 查询超过本次450条上限或官方单查询覆盖范围，任务如实 partial；框架查询返回34条完整结果。
真实任务记录：2 succeeded、5 partial、1 failed。最初失败来自 gzip 重复解压，已补回归修复并成功重跑；
保留失败历史，没有回写为通过。partial 不推进成功时间，MCP 尚有后续 cursor，不宣称任何来源全量完成。

已导出本机 Git 忽略文件：

- artifacts/p02/review-ready-20261018.json：123个有实际 README 的待审候选。
- artifacts/p02/review-all-20261018.json：全部1360个待审资产。
- artifacts/p02/data-validation-20261018.json：上述计数、来源、状态和实际窗口证据。

审核队列含真实来源说明、哈希、URL、候选分类与**空中文模板**；并非123篇已完成中文介绍。
没有真实人类审核材料或确认，本轮没有执行生产数据 publish。

## 实际自动化检查

| 检查 | 实际结果与边界 |
| --- | --- |
| Ruff / 格式 | check通过，38个Python文件格式检查通过；仅整理本次修改的源码/测试 |
| 后端 Pytest | **69 passed，无跳过**；41个单元/规则/外部HTTP替身等测试，28个真实 PostgreSQL 集成测试 |
| PostgreSQL | 独立 agentradar_test；包括迁移往返、身份/多对多、中文查询、发布隔离、锁、补跑、恢复和版本切换；不使用 SQLite |
| 保护性误配 | 以不可连接、名称非 _test 的地址验证，预期在 fixture 入口拒绝，未触发连接/迁移/清理 |
| 浏览器正常 | Edge headless **15 passed**，含P00/P01、375/768/1440布局、键盘、未知助手上下文；演示空/损坏响应测试仍明确使用替身 |
| 真实数据库故障 | 停止本项目 db，健康页 **2 passed**；新增目录 API 实测503、统一错误和关联请求 ID；之后恢复 |
| 真实 API 故障 | 停止本项目 api，健康页 **2 passed**；之后恢复 |
| 前端 | ESLint、TypeScript、Windows生产构建已实际通过；本阶段未改前端实现，Docker前端复用相同构建缓存 |
| Compose | 新依赖/迁移/后端镜像实际构建并启动；web/api/db恢复 healthy，migrate退出0 |
| 最终容器配置 | 后端令牌非空且同步关闭；web与迁移容器无GitHub令牌，镜像内无/app/.env；真实未发布详情404、公开列表/分类/趋势200且空 |
| 依赖 | pip check通过；完整固定版本锁已更新；未安装全局包 |
| 凭据与文档 | 版本控制候选扫描无令牌；真实.env和审核产物均被忽略；文档本地链接检查无缺失 |
| CI | 已更新后端真实PG迁移一致性检查，保留前端/Compose浏览器作业；**本轮没有提交推送或验证远端 Actions** |

核心行为先写失败测试再实现；新增回归确实观察到来源回退、草稿分类泄漏、中断批次跳页、压缩响应等失败后修复。
运行中保留1条已知上游 Starlette TestClient/httpx 弃用警告，没有隐藏警告或为此升级无关依赖。

中文检索实测为真实 PostgreSQL 中4条合成资产（2条已审测试夹具），不是生产中文内容：
知识库命中1、中文标签命中2、未知中文词命中0、字面量100%命中1、下划线命中0。
本次单次 HTTP 耗时保存在 artifacts/p02/chinese-search.json；只是本机小样本观察，不是生产性能或召回率承诺。
原文、结构化字段、已审版本及空结果均未使用英文全文检索代替中文验证。

## 本地运行与手工验收

```powershell
docker compose up -d --build --wait
# 浏览器 http://localhost:3000/status；产品页仍有明确的演示标签。
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:8000/api/v1/assets
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m app.cli stats
.\.venv\Scripts\python.exe -m app.cli jobs
```

公开池当前为空是正确隔离结果，不可临时开后门把采集池全量显示。审核、中文导入与发布命令见
[采集运维](../operations/p02-ingestion.md)，全新环境和独立测试库准备见根README。

## 已知限制与验收结论

- 工程、真实来源、小样本和≥1000采集规模已验证；**人工中文与发布池未完成，因此P02整体验收尚未通过**。
- 仅有限查询/目录片段，真实来源全量、长期连续调度、多日趋势、实际安装与安全性均未验证；有限状态不冒充全量成功。
- ILIKE 是子串回退，没有分词、同义词或大规模性能验证；原文/未审中文不进入公开检索。
- Skill仅显式可信目录、简单字符串frontmatter；多行YAML和未闭合内容明确拒绝，不自动采集未知Skill目录。
- 维护依赖操作系统/容器权限；审核人是显式录入，没有登录、组织权限、生产审计或公网部署保障。
- 规则分类为候选；公开分类来自已审内容。没有完整运营审核后台，人工产能仍是发布瓶颈。
- 继承P00已记录的锁文件哈希、TestClient/httpx2、Compose特殊字符密码拼接等债务，按计划在P09评估。

下一步仍在P02：使用真实README候选起草中文，真实人类审核后达到≥100且每类≥20，再验收发布池。
P03的最小输入已经稳定为四个查询API、UUID/slug、分类/difficulty/错误/未知项契约，需另获阶段授权。
建议提交信息：`feat: add P02 asset ingestion and controlled publishing`。等待用户验收后再提交，不自动推送。
