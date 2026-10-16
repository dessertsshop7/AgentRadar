# 指标、漏斗与事件字典

2026-10-17，P01 设计建议。当前没有分析 SDK、业务事件、测评用户数据或实际指标。
P00 工程请求日志只能说明服务请求情况，不能还原工具尝试和应用成功。
以下窗口、证据与去重是待确认口径，不是已取得的产品表现。

## 北极星建议

**近 28 天内，自报完成至少一次有效业务应用的测评参与者数。**

统计对象为同意测评后获得的匿名 `participant_id`，不是实名人数；同一 ID 在 28 天内最多计 1 人。
有效记录须同时具备：真实 `tool_id`、`scenario_id`、已提交的 `trial_id`、`outcome=success`、结果说明和 `evidence_type`。
未关联尝试、重复提交、演示条目、测试流量和撤回同意后的数据不进入口径。
该指标是数量，没有分母；辅助转化率另定义分母，不把数量与比例混写。

选择依据（假设）：比浏览/点击更接近“工具帮助任务完成”的产品目标。
局限：自报偏差、失访、匿名标识跨设备重复/清除、样本小；不能当平台验证成功或归因因果证据。
单独报告 `self_report` 与未来 `reviewed_artifact`（人工核实的脱敏证据）；没有核验不能升级证据等级。
P01 完成原型任务只算交互验收，不进入北极星。

## 漏斗口径

统一使用服务端收到的 UTC `received_at`，业务展示明确时区；窗口 `[start, end)`，避免边界重复。
28 天为测评队列窗口；每人从该窗口内首次有效发现/选型开始，观察后续 14 天，未满 14 天单列未成熟队列。
每层按同一 participant_id 且同一 trial/scenario 链路去重，不能把不同工具的无关点击拼成一次成功。

| 指标 | 分子 / 分母（统计对象） | 窗口与限制 |
| --- | --- | --- |
| 发现→理解 | 进入发现后看过至少一项真实工具详情的参与者 / 队列内有效 discovery_view 参与者 | 首次发现后 14 天；匿名 ID 去重；详情观看不等于理解，可另做任务复述 |
| 选型完成率 | 实际展示非空候选的 request_id 数 / 有效需求提交 request_id 数 | 28 天提交队列，14 天观察；同一 request_id 重试去重；无匹配单列 |
| 候选→外链率 | 点击候选工具官方试用入口的参与者 / 看过候选的参与者 | 同一选型链路 14 天；来源文档点击另计，不代表安装 |
| 外链→自报尝试 | 提交已尝试 trial_id 的参与者 / 点击过试用入口的参与者 | 同工具/场景、14 天；不是从点击推断尝试；直接尝试者另列，不强塞漏斗 |
| 尝试→自报成功 | 至少一次有效 success 的 trial_id 数 / 已提交尝试的 trial_id 数 | 每条尝试观察 14 天；尚无结果仍在分母并单列，不能默认为失败 |
| 结果已知率 | 有 success/failure/not_continued 结果的 trial_id 数 / 已提交尝试的 trial_id 数 | 14 天成熟队列；unknown/pending 单列；避免失访被隐藏 |
| 支持解决率（增强） | 带验证反馈的 resolved 会话数 / 有效支持会话数 | 建议 28 天会话队列、14 天观察；无反馈不算解决，证据类型拆分 |

不设首轮虚构达标值。实际邀请范围、观察期限与是否采集事件，须在接入前确认。

## 共同属性与去重

- `event_id` UUID，接收端唯一约束；`event_name`、`schema_version`、`occurred_at`、`received_at`。
- `participant_id` 为有同意的匿名测评 ID；`session_id`、`page_view_id` 按需要带入，不使用设备指纹。
- `source_environment=production|evaluation|demo|test`，`data_origin`；demo/test 永远排除产品统计。
- 相关实体 `tool_id`、`content_version_id`、`scenario_id`、`selection_request_id`、`trial_id`、`rule_version` 按事件必需。
- 重传用相同 event_id；统计再按上表对象去重。相同按钮多次真实点击可保留事件，但比例按参与者/链路去重。
- 不采集需求原文、日志原文、API Key、完整 URL 查询或证据附件到分析系统；搜索仅记录长度、筛选值和结果数，需词频时另行评估。
- 同意、撤回、保留期限及跨设备关联尚未实现。建议最小化数据与有限保存期，具体期限待确认（PRD H04）。

## 事件字典（均为未来计划）

共同字段不在每行重复。分母见漏斗表；事件本身是观测，不自动形成转化。

| 事件 | 触发条件 | 必要业务属性 | 来源/可观测范围 | 计划接入阶段 |
| --- | --- | --- | --- | --- |
| `discovery_view` | 有效真实目录完成呈现，每次 page_view_id 一次 | `page_view_id, catalog_version, result_count` | 前端可见完成；不代表读懂 | 后续 MVP F07 |
| `search_applied` | 用户提交查询/筛选并得到正常结果（含零结果） | `page_view_id, query_length, category, difficulty, result_count` | 前端 + 查询响应；不记录原始词 | 后续 MVP F07 |
| `tool_detail_view` | 真实详情正文可见，每 page_view_id/tool 一次 | `tool_id, content_version_id, page_view_id` | 前端；不代表安装/理解 | 后续 MVP F07 |
| `source_link_clicked` | 用户点击来源证据文档 | `tool_id, source_reference_id, link_kind` | 前端点击；不可观察外部阅读 | 后续 MVP F07 |
| `assistant_request_submitted` | 服务端校验通过并接受真实规则选型请求 | `selection_request_id, scenario_id, technical_constraint, rule_version` | 后端，不采需求原文到事件 | 后续 MVP F03/F07 |
| `candidate_view` | 对应真实候选结果可见；空列表亦记录 result_count=0 | `selection_request_id, candidate_tool_ids, result_count, rule_version` | 前端 + 结果版本；非空才算选型完成 | 后续 MVP F03/F07 |
| `trial_guide_view` | 用户展开/进入试用指引 | `tool_id, content_version_id, guide_version` | 前端；不是实际操作 | 后续 MVP F04/F07 |
| `tool_external_link_clicked` | 点击官方试用/仓库入口 | `tool_id, source_reference_id, link_kind, selection_request_id?` | 前端；不知是否安装、运行或完成任务 | 后续 MVP F04/F07 |
| `trial_feedback_submitted` | 用户明确反馈已经尝试，服务端成功保存 | `trial_id, tool_id, scenario_id, tried_at, evidence_type=self_report` | 后端保存成功，不由点击推断 | 后续 MVP F05/F07 |
| `outcome_feedback_submitted` | 服务端保存成功/失败/未继续/尚无结论的反馈 | `trial_id, outcome, evidence_type, reason_category, feedback_version` | 后端；自报成功和人工核实证据分开 | 后续 MVP F05/F07 |
| `support_request_submitted` | 合法脱敏问题保存成功 | `support_id, tool_id, environment_version, issue_category` | 后端；仅代表请求受理 | 增强版 F11 |
| `support_resolution_feedback_submitted` | 用户验证并提交结果，保存成功 | `support_id, resolution, evidence_type, knowledge_version?` | 后端；建议生成不算解决 | 增强版 F11 |
| `content_review_completed` | 维护者完成内容审核且事务提交 | `tool_id, content_version_id, review_decision` | 维护端/后端；数据质量指标，不混入用户漏斗 | P02 候选先记录审核业务日志，分析接入另定 |

HTTP 请求 ID 用于链路排查，事件 ID 用于统计幂等；二者用途不同，可关联但不能互相替代。
结果反馈允许修正；保留版本，以观察截止点前最新有效版本统计，不能重复累计为多个成功。
如果未取得同意或无法关联匿名 ID，可保留必要工程日志，但不能伪造完整用户漏斗。

## 接入门槛

1. 先确认测评同意、匿名 ID、撤回与保存期，定义真实目录和测试环境排除规则。
2. F03/F05 有真实保存结果后再接核心事件；用重复发送、修改反馈、零结果和未成熟队列核对统计。
3. 先提供可复算的脱敏报告；`/admin/analytics` 在鉴权和聚合权限具备后才实现。
4. 当前只交付字典与建议，没有事件 SDK、数据看板、埋点请求或宣称实际成功率。
