# P02 采集、恢复与受控维护

2026-10-18。只采集官方 GitHub REST/Search 与 MCP Registry。原文、Skill 和注册字段均为不可信数据，
不执行其中命令，不安装第三方 MCP Server，不访问登记的任意远程服务。

## 配置与执行边界

根目录真实 `.env` 保存 GITHUB_TOKEN（已在本机认证验证），不纳入 Git/镜像；Compose 只将它传给 API。
GitHub 插件登录不等于后端拿到令牌。无需 LLM Key，本阶段没有模型调用。
新增生产依赖仅为 httpx（从开发依赖移入）和 APScheduler 3.11.x；版本及传递依赖记录在锁文件。

默认 SYNC_ENABLED=false。开启时，API 启动立即后台检查，之后每 60 秒检查是否距上次成功计划超过
SYNC_INTERVAL_HOURS（默认 24）；不是每分钟全量采集。关闭/重启不回放错过的历史周期。
默认单次上限为 GitHub 1500 条、README 30 次、MCP 100 条，可用对应 SYNC_* 配置调整。
测试默认不接通真实外部同步。调度在 API 进程内，每个来源仍由 PostgreSQL 事务级 advisory lock 跨进程互斥。

锁连接只持锁，数据使用短事务提交；中断/取消释放锁。下一次取得锁后将遗留 running 标为 interrupted，
随后幂等重采。普通健康查询使用独立会话，不等待外部 HTTP 完成。APScheduler 无持久化日历任务，
持久化业务时间和检查点在 PostgreSQL，不引入 Redis/队列。

## 从根目录运行（PowerShell）

```powershell
docker compose up -d --build --wait
$env:PYTHONPATH = 'apps/api'
# 以下均使用根目录 .env 的开发库，不是测试库。
.\.venv\Scripts\python.exe -m app.cli --help
.\.venv\Scripts\python.exe -m app.cli sync --source github --query 'repo:modelcontextprotocol/python-sdk' --max-records 1 --readme-limit 1
.\.venv\Scripts\python.exe -m app.cli sync --source mcp --max-records 100
.\.venv\Scripts\python.exe -m app.cli stats
.\.venv\Scripts\python.exe -m app.cli jobs
```

不用宿主机 Python 时，可执行 `docker compose exec -T api python -m app.cli stats`，其他命令同理。
维护权限来自操作系统/容器访问权与数据库凭据；没有匿名写 HTTP、用户登录或管理后台。
CLI 退出码：正常/locked/not_due 为 0；partial/failed/interrupted 为 2；输入或内部错误为 1。
partial 不等于完整同步成功，应查看任务 coverage 和 errors；日志只给安全代码/数量，以 job_id 关联。

## 来源与失败策略

GitHub 默认按 rag、ai-agent、mcp、llm-framework 主题和 Stars 区间划分近期（180 天）查询。
Search 每查询至多处理 1000 条，按 Link 翻页、按稳定 ID 去重；达到配置上限、incomplete_results 或超出
接口覆盖时记录 partial，不声称 GitHub 全量。自定义 --query 是本次计划范围，最近成功计划不代表全库刷新。
数值未变也可保存另一个真实任务的快照；原始 metadata 单独更新，不用 Stars 变化制造内容版本。

README 根据 readme_checked_pushed_at 粗筛，再以 ETag 条件请求、最终哈希判定变化；pushed_at 不等于正文变化。
304 或哈希未变不生成新版本。文档缺失记录 README_MISSING，不伪造文本，覆盖率另算；有旧证据但无法重新读取时标记待核实。
301 仅跟随相同官方 API origin，保留稳定 ID；404 不等于确认删除，不向任意重定向地址转发凭据。

HTTP 单次 15 秒超时，整体请求/退避流程最多 45 秒，最多 3 次尝试，解压后正文上限 3 MB。
403/429 按 Retry-After/主限额头退避；需等待超过 30 秒时结束当前请求并保存重试依据，避免占住请求任务。
认证失败/权限不足不盲目重试；5xx/连接问题有限重试。同步失败至少退避 10 分钟，主限额等待更长时尊重响应头；
仅定额截断则等正常同步间隔再试，不反复轰炸相同范围。
正确鉴权的 304 仅免主限额，仍要遵守次级限制。[GitHub 官方建议](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)

MCP 使用 v0.1、version=latest、opaque cursor；断批只在整批成功后推进检查点，部分入库后中断会重放本批。
新一轮增量使用前一完整扫描开始时刻作为 updated_since，允许重叠并去重，避免扫描期间新增/更新被跳过。
未扫完整个范围不推进 last_success_at；current cycle 的检查点保存在 job.coverage。
官方目录公开可读，但登记声明不等于安全审核。[官方 API](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/api/official-registry-api.md)

## 人工内容闭环

默认走以下人工流程；本轮明确委托的 AI 代审使用后面的独立路径，不将 AI 审核记为人类确认。

```powershell
$env:PYTHONPATH = (Resolve-Path .\apps\api).Path
.\.venv\Scripts\python.exe -m app.cli export-review --output artifacts/p02/review-queue.json
# 优先处理有 README 证据的候选：
.\.venv\Scripts\python.exe -m app.cli export-review --with-readme --output artifacts/p02/review-ready.json
# 打开清单核对真实来源，编写一个 ContentDraft JSON；不要把整份导出清单作为内容 JSON。
.\.venv\Scripts\python.exe -m app.cli draft --asset '<资产 UUID>' --source-hash '<清单中的来源哈希>' --file artifacts/p02/content.json
# 由实际审核人核实后，使用上一步返回的版本 ID；开发助手不得代签此命令。
.\.venv\Scripts\python.exe -m app.cli publish --version '<内容版本 UUID>' --reviewer '<真实审核人>' --confirm-human-review --note '<核对依据>'
.\.venv\Scripts\python.exe -m app.cli withdraw --asset '<资产 UUID>' --reviewer '<维护人>' --confirm-human-review --note '<撤下依据>'
```

ContentDraft 必需字段：summary_zh、categories；可选 name_zh、description_zh、difficulty、cost、tags、
scenarios、requirements、limitations、origin。origin 为 human 或 assistant_draft；未知项保留 unknown。
导出清单包含空中文模板，明确待审核，不是已经制作/批准的产品介绍；导出命令不修改数据库或发布任何条目。
导出拒绝覆盖已有文件，避免丢失人类编辑结果；再次导出用新文件名。大批源数据与本机审核清单不入 Git。

### 本地中文待审稿（2026-10-18）

本次已将 `review-ready-20261018.json` 中全部 123 个有 README 证据的候选整理为中文介绍，
位于 `artifacts/p02/review-zh-20261018/`。打开 `index.html` 可搜索、筛选和展开阅读，
或阅读同目录的 `中文审核稿.md`；可直接按编号在聊天中反馈“通过 / 修改 / 暂缓”，无需先运行 CLI。
页面用于阅读，不保存审核决定。`drafts/` 为逐条 ContentDraft JSON，`sources/` 为原始 README 纯文本副本，
`review.json` 保留资产 ID、来源哈希、内容哈希、证据行号及中文稿的对应关系。

中文内容由开发助手依据已采集资料整理，均标记 `assistant_draft`，没有调用项目的模型 API，
没有重新联网确认、安装或运行第三方项目，也没有导入数据库或发布。场景、分类、门槛与审核优先级为助手建议；
费用统一为未知。原始来源的声明、助手推断与尚未验证的效果须分开理解。
停止维护、测试版本、资料合集、简介与正文不一致等情况在各条目中列出；它们不因翻译完成而自动符合发布条件。
人工确认内容后再使用现有 `draft` / `publish` 命令，仍须核对当前来源哈希和实际审核人；不批量代签。
本地稿件与来源副本沿用 `artifacts/` 忽略规则；阶段提交不自动包含这些文件。

### 事实审校修订版（2026-10-22）

当前审阅入口更新为 `artifacts/p02/review-zh-20261022/index.html` 和同目录的 `中文审校修订稿.md`，
10 月 18 日原版保留。已逐项复核 123 个官方仓库、非空 README 和稳定 ID，修正文案、分类、维护与许可边界。
本轮助手结论为 87 条可供最终人工确认、10 条需补证据、26 条建议暂缓；不是人类审批或发布结果。
44 份 README 与 19 项关键元信息变化，合计 58 条须先重新同步，不能把新说明绑定旧来源哈希。
仅导出 45 份文件级条件满足的 JSON；当前开发数据库连接未成功，导入前仍由 CLI 核对即时版本。
范围、主要修正、官方依据及验证限制见 [内容事实审校记录](p02-content-review-20261022.md)。

### 本轮委托 AI 审核已执行（2026-10-28）

用户明确授权由 AI 完成全部资料审核、补证据、暂缓与可逆发布，无需逐条人工确认。
已核对并受控刷新 133 项真实来源，发布 103 项，记录 30 项暂缓；完整结果见
[委托审核报告](p02-delegated-review-20261028.md)。10 月 18/22 日记录是当时结果，不代表当前公开池。
每条中文内容保留 `origin=assistant_draft`，审核人 `ai:codex`，类型 `delegated_ai`，不使用人类确认标志。

以下是该路径的维护命令示例，**仅在有明确用户委托时使用**；占位符须替换为实际清单值：

```powershell
$env:PYTHONPATH = (Resolve-Path .\apps\api).Path
.\.venv\Scripts\python.exe -m app.cli publish --version '<内容版本 UUID>' --reviewer 'ai:codex' --confirm-delegated-ai-review --authorization-ref 'artifacts/p02/delegated-review-20261028/authorization.json' --note '<已核对的依据与限制>'
.\.venv\Scripts\python.exe -m app.cli defer --asset '<资产 UUID>' --source-hash '<当前来源哈希>' --reviewer 'ai:codex' --confirm-delegated-ai-review --authorization-ref 'artifacts/p02/delegated-review-20261028/authorization.json' --note '<暂缓原因与证据>'
```

人工确认和委托 AI 确认参数互斥；AI 路径要求 `ai:` 审核人和非空授权依据。CLI 不提供身份认证，
授权依据的真实性由具备操作系统/数据库维护权的操作者负责，不能把填入路径当成权限系统。
暂缓追加有原因、来源哈希、审核者和时间的决策版本，不发布、不删除历史；后续有新证据可重新评估。
本轮完整中文结果在 `artifacts/p02/delegated-review-20261028/审核执行结果.md`，不是等待用户逐条审批的队列。
`decisions.json`、`execution-ledger.jsonl`、`verification.json` 分别保存结论、实际事务结果和真实 API 核验。
这些本机产物和操作前数据库备份受 Git 忽略规则保护，不自动随代码推送。

Skill 只接受操作者明确指定的可信根目录：

```powershell
.\.venv\Scripts\python.exe -m app.cli inspect-skill --trusted-root '<可信目录>' --file '<可信目录>/SKILL.md'
```

仅支持简单 frontmatter 的 name/description，限制文件大小及目录边界；不执行正文，也不自动导入发布池。
不自动扫描个人 Skill 或 GitHub 上未知 Skill 目录。

## 独立测试数据库

本机已单独创建 agentradar_test；新环境须先执行以下一次：

```powershell
docker compose exec -T db createdb -U agentradar agentradar_test
$env:TEST_DATABASE_URL = 'postgresql+psycopg://agentradar:agentradar_dev_only@127.0.0.1:15432/agentradar_test'
.\.venv\Scripts\python.exe -m pytest -c apps/api/pyproject.toml apps/api/tests -m integration
```

数据库已存在时不重复创建。fixture 在任何迁移/清理前要求 PostgreSQL、显式 URL、数据库名以 _test 结尾，
再确认 current_database；只清理该库本项目模型表。缺配置明确跳过，不回退开发库，不用 SQLite 代替。
CI 自建独立 PostgreSQL 测试库，默认不访问真实 GitHub/MCP；真实冒烟与外部 HTTP 替身结果分别报告。

Linux/macOS 使用 `.venv/bin/python`，环境变量采用 `PYTHONPATH=apps/api ...`，Docker 命令一致。
