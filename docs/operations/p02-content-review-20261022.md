# P02 中文内容事实审校与修订记录

日期：2026-10-22，Asia/Singapore。范围：10 月 18 日首批 123 个具有 README 证据的候选。
这是用户授权的助手内容审校；不代签真实人类审核，不修改数据库，不启动 P03，不提交或推送 Git。

## 本次实际完成

重新通过官方 GitHub REST API 获取 123 个仓库的元数据与 README，核对稳定 ID、当前定位、维护声明、
分类、使用门槛、源码/文档/商业服务边界，并修改全部 123 条中文稿。保留 10 月 18 日原始版本。
外部文档只作为资料，没有执行其中的命令、安装第三方项目或调用项目的模型 API。

| 检查或结果 | 实际数量 | 含义 |
| --- | ---: | --- |
| 仓库元数据与稳定 ID | 123/123 | 身份一致；不靠同名推断为同一项目 |
| 具有实际正文的当前 README | 123/123 | 第 112 项的 JSON 响应省略大文件正文，已用官方 raw media 补取，未把空串当成功 |
| 许可端点取回正文 | 119/123 | 未识别的是 015、034、115、117；不等于不存在许可证 |
| README 与旧快照不同 | 44 | 不能继续用旧证据描述成当前事实 |
| 关键元信息与旧快照不同 | 19 | 说明、许可证元数据或名称变化；与 README 变化有重叠 |
| 合计需重新同步来源 | 58 | 新说明不得重新绑定旧来源哈希 |
| 可供最终人工确认 | 87 | 内容层面的助手审校结论，不代表安装、安全验证或发布批准 |
| 需补证据或修正 | 10 | 具体未决项见下文 |
| 建议暂缓首批收录 | 26 | 包括范围不适配、资料目录、维护或许可声明冲突；保留中文说明 |
| 符合 ContentDraft 的内容 | 102 | 另外 21 条主动留空不适合的分类，只作为审校说明，不伪造合格草稿 |
| 提供独立 JSON 草稿 | 45 | 只满足文档、字段及旧快照未变的文件级条件，仍待人工确认和当前库校验 |
| 本次人类批准 / 入库 / 发布 | 0 / 0 / 0 | 不计入 P02 发布池数量 |

当前 API 对这 123 个仓库均返回 `archived=false`，且近期更新条件满足。
这只反映核查时的字段，不能代替 README 的维护声明、实际维护承诺或软件运行验证。
旧稿“83 可优先 / 34 重点核对 / 6 暂缓”是初稿排序，本表是本轮内容审校结论，二者不作为通过率比较。

## 主要修正及官方依据

- **分类与资产边界**：删除仅因出现 integration、知识或框架关键词而附加的类别。
  教程、书稿、目录和纯部署示例保留资料价值，不为达到 100 条而冒充首批软件资产；没有合适分类的说明稿不导出可直接导入文件。
- **AutoGen（082）**：GitHub API 未归档，但同一 README 顶部自述停止维护，后文又提及维护模式和改进贡献，
  因此修正“已经归档”的单向结论，记录矛盾并建议暂缓。文档与代码许可也分别记录。
  依据：[README](https://github.com/microsoft/autogen/blob/main/README.md)、[代码许可](https://github.com/microsoft/autogen/blob/main/LICENSE-CODE)。
- **OpenClaude（040）**：当前许可文件自述涉及专有派生代码和未获授权分发的部分，删除“整个仓库 MIT 开源”的笼统介绍并暂缓。
  本报告记录来源自述，不判断特定使用行为是否合法。依据：[LICENSE](https://github.com/Twigpine/openclaude/blob/main/LICENSE)。
- **Teable（063）**：区分不同部署形态，独立自行部署不包含所有 AI 与应用构建能力；源码许可、完整产品镜像与付费解锁分别核对。
  依据：[部署对照及许可说明](https://github.com/teableio/teable/blob/develop/README.md)。
- **n8n、Dify、NocoBase、LobeHub 等**：不把自定义或附加条款概括成无条件免费、标准开源；
  Onyx、Activepieces 等区分核心代码和企业目录。依据示例：
  [n8n LICENSE.md](https://github.com/n8n-io/n8n/blob/master/LICENSE.md)、[Dify LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE)。
- **Graphiti（101）**：补充当前 README 对参考 MCP/REST 服务缺少认证、授权和提示注入防护的明确说明，
  与核心图谱库分开描述。依据：[当前 README 安全边界](https://github.com/getzep/graphiti/blob/main/README.md)。
- **Cua（114）**：区分当前组件、尚未发布的绑定及旧包；记录旧 `cuabot` 的来源安全警告和多组件许可，
  不按根目录单一标签描述整个项目。依据：[组件、废弃包及许可说明](https://github.com/trycua/cua/blob/main/README.md)。
- **来源质量**：DeepTutor、TrendRadar 改用正式功能正文替代更新日志、徽章与导航作为主要证据；
  PPT Master、本地助手和模型服务分别说明本机处理与外部模型调用的数据路径。

上述是文档层面事实审校，不是许可证的法律适用意见，也不是安全审计或第三方软件验收。

## 仍需补证据的 10 项

| 编号 | 项目 | 待确认内容 |
| --- | --- | --- |
| 034 | OpenGiraffe | 补充可核对的许可文件，不因端点未识别而断言无许可 |
| 045 | TencentDB Agent Memory | 团队记忆测试版与实验后端的具体使用边界 |
| 057 | Kong | 核心版本、AI 插件及托管能力的对应关系 |
| 059 | NocoBase | 完整许可及实际拟收录版本包含的 AI 功能 |
| 063 | Teable | 社区源码、完整产品与独立部署的资产归属及功能范围 |
| 067 | LibreChat | 稳定功能与 beta、高度实验性工作区的选择范围 |
| 073 | Quivr | evaluation stage / API v0 的具体版本和使用边界 |
| 074 | LobeHub | Operator 与聊天界面定位、发行版和许可对象的对应关系 |
| 080 | Serviette | Pathway 依赖、许可密钥与选用后端的配置边界 |
| 115 | PocketLLM | 离线简介与当前后端/数据服务架构差异，以及许可文件依据 |

## 查看与复核

新版本地资料位于 `artifacts/p02/review-zh-20261022/`，沿用忽略规则，不自动纳入 Git：

- `index.html`：可搜索的中文修订稿；本机预览为 <http://127.0.0.1:8766/index.html>。
- `中文审校修订稿.md`：完整文案、修改原因、许可/维护说明和逐项官方证据。
- `review.json`、`records/`：编号、内容、编辑结论与新旧来源对应。
- `sources/`、`licenses/`、`live-checks.json`：当前原文与 API 证据；保留抓取时间、文件 Git blob 和 SHA256。
- `drafts/`：45 份文件级条件满足的 JSON；未发布，也不直接代表当前数据库允许导入。
- `database-readonly-check.json`：本次开发数据库只读连接失败，错误类型 `OperationalError`，未输出连接串。

本次未能核对当前开发库的即时来源版本和发布数量，不沿用 10 月 18 日的数据库查询值冒充当前结果。
导入时仍必须由现有 CLI 核对 `expected_source_hash`；58 条来源变化先受控同步，再核对并起草。
所有条目最终发布仍需真实人工确认，目录数量目标和发布池验收保持未完成状态。

需要重开阅读页时，从根目录执行：

```powershell
.\.venv\Scripts\python.exe -m http.server 8766 --bind 127.0.0.1 --directory artifacts/p02/review-zh-20261022
```

也可直接打开本地 HTML 或 Markdown。阅读页只展示资料，不保存审批决定、不调用分析 SDK。
实际执行的来源/文件校验与浏览器结果保存到本版 `validation.json`、`browser-validation.json`。
文件检查确认：123 条来源哈希与身份匹配、530 处 README 引用有效、本地链接缺失为 0；
102 份内容通过现有 ContentDraft 校验，21 份空分类说明没有被伪造成可导入草稿。
Edge headless 实际验证了 87/10/26 结论筛选、键盘搜索、空结果恢复、展开/折叠、45 个下载入口，
以及 375、768、1440px 宽度；页面错误与外部请求均为 0。该结果不等同于真实手机或 Safari 验收。
应用代码和数据库结构未改动，因此本轮不声称重新执行后端测试、前端构建或 CI。

建议后续提交信息：`docs(p02): audit asset content against current official sources`。
本次不创建提交；P02 数据发布缺口和最终人工确认由用户继续验收。
