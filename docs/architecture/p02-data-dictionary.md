# P02 数据字典与发布规则

2026-10-18。实际迁移为 `0001_p00_baseline → 0002_p02_assets → 0003_p02_review`。
P00 空基线未修改；0003 是在测试中发现来源回退及草稿分类隔离问题后增加的演进。

## 实体与职责

| 表 | 主键、稳定标识与主要字段 | 职责及约束 |
| --- | --- | --- |
| sources | id：github / mcp；base_url、enabled、last_success_at、retry_after | 受控官方来源与最近完成计划的时间；成功时间不代表 GitHub 全量或全部仓库均已刷新 |
| repositories | 内部 bigint；source_id + external_id 唯一；full_name、canonical_url、stars、forks、license、pushed_at、source_created_at、collected_at、raw_data | 仓库事实；使用 GitHub 数字 ID 去重，改名更新地址，不改内部身份 |
| assets | UUID；source_id + external_id 唯一；slug 唯一；name、asset_type、review_state、current_source_hash、published_version_id、collected_at | 用户理解的技术资产；GitHub 默认一个目录条目，但关系支持多个资产/仓库 |
| asset_repositories | asset_id + repository_id；is_primary | 多对多关系；部分唯一索引保证一个资产最多一个主仓库；指标只取主仓库，不对关联重复求和 |
| repository_documents | UUID；repository_id + content_hash 唯一；body、source_url、etag、fetched_at | 不可变 README 来源证据；内容回退到既有哈希时复用历史文档，不覆盖正文 |
| asset_versions | UUID；asset_id + source_hash + content_hash 唯一；repository_document_id、raw_data、source_url、中文内容、categories、difficulty、cost、status、content_origin、reviewed_by/at/note | 原始来源版本与中文版本分开；内容版本绑定明确的来源哈希；已审分类随版本保存 |
| asset_categories | 稳定字符串 id、label | 四类场景词表，不是排他资产类型 |
| asset_category_links | asset_id + category_id；evidence | 规则命中及维护草稿的候选分类，可重叠；不是公开分类或人工审批证明 |
| repository_snapshots | bigint；repository_id + job_id 唯一；observed_at、stars、forks | 实际接收时点的指标，同一任务不重复，另一个真实任务可保存数值未变的观测 |
| trend_scores | asset_id；formula_version、score、components、star_growth、sample_count、window_start/end | 当前可复算趋势得分；历史原始观测保留在 snapshots，当前分数更新保存 |
| sync_jobs | UUID；source_id、trigger、status、started_at/finished_at、counts、coverage | 有界任务范围、分页覆盖、MCP 检查点、实际数量和恢复依据 |
| sync_errors | bigint；job_id、code、item_key、message、recorded_at | 安全错误代码；不保存 HTTP Authorization、连接串、异常正文或堆栈 |

比规划的九种核心实体增加三张表：README 原文共享需要 repository_documents；场景多对多需要
asset_category_links；得分版本和分项持久化需要 trend_scores。没有用户、企业或模型业务表。
外键均有可用索引；发布版本的复合外键保证不能指向另一个资产的内容版本。

## ID、类型与未知值

- GitHub 仓库 external_id 为官方数字 ID 的字符串；资产 slug 为 `gh-<id>`，改名保持不变。
- MCP 资产按 Registry server.name 标识，版本进入 asset_versions；slug 为 `mcp-` 加名称 SHA-256 前 24 位。
  不以同名合并 GitHub 和 MCP 资产；只有受控 GitHub URL 与已采集仓库匹配才增加关系。
- asset_type 为 tool / agent / skill / mcp / framework；场景可以多选，也可以待分类。
- 四类场景：knowledge、agent-workflow、mcp-integration、framework。
- difficulty 为 unknown / beginner / visual / developer；cost 默认 unknown；缺失许可证返回 unknown。
  目录登记、许可证和 Stars 都不等于安装成功、安全认证或免费可商用承诺。
- 所有持久化时间使用带时区 datetime；采集时间是实际执行时间，来源 pushed_at/created_at 单独保留。

## 版本和发布状态

`source_metadata` 是外部资料，不是中文解释；human 是操作者声明的人工作品，assistant_draft 是开发助手整理的中文内容。
P02 不调用项目 LLM API；内容来源与审核状态独立，已发布内容仍可能保留 assistant_draft。

来源哈希变化 → 新的来源草稿 → 现有发布指针保留 → review_state=needs_review。
若来源回到已审内容对应的哈希，复用历史证据，状态恢复 approved。不能靠“最新创建时间”判断当前来源。
人工中文修订另建版本，不能覆盖已审中文字段；导入必须带期待的 source_hash，过期即拒绝。

发布须满足：明确审核确认与审核人、中文摘要、版本中的场景分类、有效来源哈希与可追溯 URL。
GitHub 条目还需实际 README、未归档、来源可用且最近 180 天有 push。未知费用和门槛可以保留 unknown。
命令中的审核人为操作者明确录入，没有账号认证或企业级审计，不冒充已验证的人类身份。

2026-10-28 本轮用户明确委托 AI 代审，使用既有 `asset_versions.raw_data.review` 保存
`actor_type=delegated_ai`、`decision` 与 `authorization_ref`；审核人记录 `ai:codex`。
默认人工路径记录 `actor_type=human`，拒绝 `ai:` 审核人使用人工确认；旧版本未记录类型时公开返回 unknown。
本轮还保存决策清单/授权文件哈希、README blob、官方元数据和许可文件哈希、证据行及类型修正前后值，
不覆盖原始资料版本；没有新增字段或表，因此无需新迁移，迁移 head 仍为 `0003_p02_review`。

暂缓收录追加 `status=rejected` 的决策版本，`raw_data.review.decision=deferred`，保存原因和审核时间。
资产仍为 pending、没有 published_version_id；pending 表示未发布且可在新证据出现后重新评估，不表示本轮漏审。
已发布资产不能用暂缓命令覆盖，应走独立撤下流程。暂缓命令要求当前来源哈希，重复同一决定复用版本。

公开读取仅使用 published_version_id 指向的已审版本；列表、详情、趋势和分类计数统一过滤。
needs_review 时只显示原已审版本并提示待重审；新中文、标签与分类不会泄漏。
未发布、撤下、来源待核实条目的公开详情均为 404。缓存最长 30 秒，撤下并非跨客户端即时撤回。

301 仅跟随同一官方 API origin，保持 ID；404 表示不存在或不可访问，先标记 unverified，暂停公开展示。
操作者核实后可撤下资产，保存说明版本及原发布指针，不删除历史。恢复发布前需要重新核实来源。

## 计数与趋势

采集池以去重 GitHub 仓库计数；MCP 资产和资产总数另外报告。规则分类可重叠，同一资产在每类最多计一次；
发布池总数按不同资产计一次，分类配额分别计数，不能把类别之和当作发布总数。

`p02-v1`：50% 增长 + 25% 活跃 + 15% 新鲜 + 10% 完整性。
增长分项为 `min(100, log(1+max(0,delta))/log(1001)*100)`；活跃按距 push 的 180 天线性衰减，
新鲜按创建后的 365 天线性衰减；有 README 完整性为 100，否则 50。
窗口为最近一次观测之前最多七天中实际存在的观测，返回实际起止时间。
不足两个不同时间点时 growth 与 star_growth 为 null，增长分项不贡献总分；负增长保留原 delta，得分贡献为零。
即使窗口只有几分钟，也只代表这几分钟，不能标为七日增长或 GitHub 官方 Trending。
