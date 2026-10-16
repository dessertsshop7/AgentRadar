# P01 产品与原型基线

日期：2026-10-17（Asia/Singapore）。本阶段交付产品规划和有限原型，不实现真实业务处理。
开始时 Git `main` 与 `origin/main` 一致（P00 `44d9c77`），没有用户未提交改动；API/web/db healthy。
未发现影响本阶段的 P00 阻断问题。已有页面只做工程检查，已有样式为普通 CSS，尚无产品文档或业务组件。

## 产品基线

- 首要用户为有明确任务的产品运营，次要为初学者，完整技术支持能力在增强版；这是待验证假设。
- 首页直接进入发现；单一目录避免重复首页。真实状态入口从 `/` 迁至 `/status`，后端契约不变。
- MVP 规划为真实目录/解释 → 规则选型/试用准备 → 尝试与结果反馈；P02 仅建议最小真实目录，不自动开工。
- 28 条用户故事关联 F01–F16；模型辅助 F15 后续独立评估。规划验收与 P01 原型验收分开记录。
- 北极星建议为 28 天内自报完成有效业务应用的匿名测评参与者数；自报、外链、尝试和核实证据分开，不展示运营假数据。

七份产品文档的职责：

| 文档 | 内容 |
| --- | --- |
| [PRD](../product/prd.md) | 定位、规则、28 个故事、P01 验收、P02 实体/字段/接口候选和 H01–H06 |
| [画像](../product/personas.md) | 三类假设用户及优先级取舍 |
| [旅程](../product/user-journeys.md) | 三条端到端任务，包含失败、退出、恢复与事件 |
| [优先级](../product/feature-priority.md) | F01–F16 的价值、依赖、阶段、理由与验收 |
| [信息架构](../product/information-architecture.md) | 全部指定路由、职责、关系、开放与权限依赖 |
| [设计规范](../product/design-system.md) | CSS 令牌、组件、内容/状态、键盘与响应式规则 |
| [指标](../product/metrics.md) | 北极星、漏斗、事件、分母/窗口/去重、观测与证据限制 |

## 实现边界与文件职责

- `apps/web/app/layout.tsx` + `components/site-header.tsx`：统一外壳、跳过导航、可用入口、当前页。
- `app/discover/page.tsx` + `components/discover-catalog.tsx`：异步 searchParams、GET 表单和 URL 条件，客户端对六条演示数据过滤。
- `app/tools/[slug]/page.tsx`：服务端读取唯一演示文件，展示适用、不适用、条件、来源；不存在使用 `notFound()`。
- `app/assistant/page.tsx`：只传工具名称、slug 和分类上下文；`components/assistant-panel.tsx`：本地校验、固定规则和结果焦点。
- `public/demo/catalog.json`：所有虚构工具信息的唯一源；没有真实仓库、stars、采集时间、成功率。
- `lib/catalog-types.ts`：页面使用的数据类型及静态响应结构检查；`lib/demo-catalog.ts`：服务端读取；`lib/use-demo-catalog.ts`：客户端静态读取、5 秒超时、取消与手动重试。
- `components/demo-notice.tsx`、`tool-card.tsx`、`catalog-state.tsx`：实际复用的演示提示、卡片和状态；没有预建未来组件库。
- `app/status/page.tsx`：承接原工程页，保留原 `health-panel.tsx`；真实健康逻辑没有改动。
- `app/loading.tsx`、`error.tsx`、`not-found.tsx`：路由级恢复界面；错误回调按安装版 16.4.2 使用 `retry`。
- `app/icon.svg`：与导航品牌一致的浏览器图标；补充审查定位到浏览器默认 `/favicon.ico` 404，添加图标约定后实际图标请求 200、控制台错误消失。
- `app/globals.css`：浅色中文目录、语义色、三档布局、焦点与内容折行；无新增依赖，锁文件不变。
- `infra/web.Dockerfile`：补充复制 `public/`，使生产镜像可提供静态演示目录。
- `tests/e2e`：健康页迁址验证 + 产品原型核心流程；CI 正常场景运行全部，故障场景只运行健康测试。

请求链路：发现/助手 HTML → 浏览器 `GET /demo/catalog.json` → 本地虚构目录；详情由服务端读取同一文件。
搜索通过 Next Form GET 导航更新 URL，不调用业务 API。助手输入和结果只在页面内存，没有 POST、分析 SDK 或模型调用。
工程页独立走浏览器 → `/api/v1/health` → 真实 PostgreSQL。端口、CORS、配置、数据库卷与迁移沿用 P00。
没有后端业务代码、表结构或 Alembic 变化，没有导入这些虚构条目到 PostgreSQL。

固定演示规则（不使用文本语义）：

| 场景 | 不能写代码 | 有开发支持 |
| --- | --- | --- |
| 知识管理 | 团队知识库问答助手 | 文档结构化处理工具箱 |
| 内容运营 | 内容选题整理助手 | 运营流程编排工作台 |
| 技术支持 | 支持问题分类与交接助手 | 支持资料连接器 |

支持场景的低代码案例仍需配置，选择“不能写代码”时明确提示不应视为满足条件。没有真实匹配分数或成功保证。
其他规划路由没有可点击空入口；收藏、支持、后台、工作台、模型和真实反馈均未实现。

## 运行与复现

完整从零安装和迁移见根 README。已有 P00 配置时，从根目录：

```powershell
docker compose up -d --build --wait
# http://localhost:3000/discover
# http://localhost:3000/tools/knowledge-base
# http://localhost:3000/assistant
# http://localhost:3000/status

npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run typecheck
npm.cmd --prefix apps/web run build
.\.venv\Scripts\python.exe -m ruff check --config apps/api/pyproject.toml apps/api tests
.\.venv\Scripts\python.exe -m ruff format --check --config apps/api/pyproject.toml apps/api tests
$env:PLAYWRIGHT_CHANNEL = 'msedge'
$env:HEALTH_SCENARIO = 'healthy'
.\.venv\Scripts\python.exe -m pytest -c apps/api/pyproject.toml tests/e2e -m e2e
```

健康故障场景使用 README 的停止/恢复命令，只对本项目 db/api 操作，不清数据卷。
Linux/macOS 使用 `.venv/bin/python`、`npm` 和相应环境变量语法；CI 使用项目内 Chromium。

## 本轮实际验证

| 验证 | 结果 |
| --- | --- |
| TDD 起点 | 新原型 + 迁址健康测试共 12 项预期失败，缺少页面/入口；没有把 404 或超时写成通过 |
| 开发预览与补充回归 | 第一轮 10 项原型测试通过；卡片动作测试先失败后修正。另先复现“有效结果后提交无效需求仍保留旧结果”，补最小状态清除并通过最终回归 |
| ESLint / TypeScript | 最终版本通过，无新增依赖 |
| 生产构建 | Windows 本地和 Linux Docker 均通过；public 演示文件进入运行镜像 |
| Ruff | check 与 format check 通过，21 个 Python 文件 |
| 后端回归 | 19 passed：16 个替身单元测试 + 3 个真实 PostgreSQL 集成测试；1 条 P00 已记录的上游弃用警告 |
| 生产容器浏览器正常场景 | 最终 **14 passed**：12 项原型用例 + 2 项真实健康用例；包括三个宽度、纯键盘流程、搜索/筛选/刷新 URL、六条目录、演示输入、旧结果清除、加载/空结果/读取失败/重试与缺失详情 |
| 真实数据库/API 故障 | 停止本项目 db 后 **2 passed**（真实 503）；恢复后 HTTP 200。停止 api 后 **2 passed**（真实不可达）；已恢复，web/api/db healthy，migrate 仍 Exited (0) |
| 额外界面审查 | 三页 × 375/768/1440/812px 横屏共 12 组布局检查通过；长中文标题、多标签、合成长 URL、可见控件标签无异常；6 个固定规则组合均核对正确，低代码限制提示有效；无页面/控制台错误、无业务 POST |
| GitHub Actions | 已更新配置；本表记录本地验收，远端结果须以实际 GitHub 工作流记录为准，不据此宣称 CI 通过 |

测试分层：正常原型读取实际静态演示文件；健康检查访问实际 API/PostgreSQL。
仅空目录与损坏目录测试使用 HTTP 响应替身；网络失败测试中断静态请求后放行重试。
加载测试暂缓并继续真实静态请求，健康加载测试也只暂缓真实 API 请求。
这些交互测试均不证明真实工具推荐、安装、业务应用、采集或模型效果。

截图与额外审查证据位于本机忽略目录 `artifacts/p01-*.png`、`artifacts/p01-ui-audit.json`；不是运营数据。
产品文档按 F/US/事件/路由逐项人工交叉审查，不为中文文档和简单配置编写形式化测试。

### Web Design Guidelines 针对性审查

- `apps/web/components/tool-card.tsx:19`：已修复，卡片动作是实际 Link，标题和动作触控高度均至少 44px；回归通过。
- `apps/web/app/icon.svg:1`：已修复浏览器默认图标 404；实际声明的图标资源返回 200，干净浏览器无控制台错误。
- `apps/web/components/discover-catalog.tsx:30`：通过，原生 GET 表单、字段标签、可重放 URL 和清除/错误恢复。
- `apps/web/components/assistant-panel.tsx:37`：通过，空白输入校验、保留字段、错误焦点、旧结果清除；结果标题焦点与演示说明可用。
- `apps/web/app/globals.css:32`：通过，可见焦点与 44px 主操作；响应式、长内容折行和 reduced-motion 已检查。
- 八组语义颜色计算通过：正文/白底 14.67:1、次要文字/背景 5.88:1、白字主按钮 6.87:1；控件边界/白底 3.43:1、焦点/白底 5.78:1。
- 已人工查看生产模式桌面发现、375px 长标题详情、平板与助手结果截图；没有发现审查范围内的内容遮挡。未开展完整屏幕阅读器认证。

本地 P01 文档与原型验收条件已满足；产品假设仍待真实测评。交付报告后，用户已明确授权本地提交与推送。

## 已知限制与下一阶段

- 首要用户、需求优先级与北极星仍是假设；没有实际用户访谈或成功指标。
- 演示案例不可安装，不持久化任务/结果；无收藏/身份/分析/部署排障能力。未知路由有恢复页面，不代表功能开放。
- 路由错误边界已实现，但没有刻意在生产代码加入抛错开关；故障自动化主要验证目录读取与真实健康链路。
- Windows Edge headless 是当前浏览器验证环境，不等于真实手机、Safari/Firefox 或完整屏幕阅读器验收。
- 只有浅色主题；保留 P00 上游 TestClient 弃用警告与依赖取舍，不扩大本阶段升级范围。
- P02 建议输入已在 PRD 定义：Tool/SourceReference/ToolContentVersion、受控导入、公开只读目录/详情 API。
  必须使用真实已审查来源、新 Alembic 迁移和真实 PostgreSQL 验证；中文检索与枚举/审核规则需要实测。
- 助手、尝试/反馈、事件、支持、身份与企业接口分属后续范围，不随 P02 目录一起提前建立。

本次按用户指令提交并推送 P01 交付，不进入 P02。
建议提交信息：`feat: define P01 product baseline and interactive prototypes`。

## 技术参考（核对日期 2026-10-17）

- Context7 解析 `/vercel/next.js`，查询异步 params/searchParams 与 Next Form GET 导航；
  [动态路由](https://nextjs.org/docs/app/api-reference/file-conventions/dynamic-routes)、
  [Form](https://nextjs.org/docs/app/api-reference/components/form)。
- 同时阅读本地 Next.js 16.4.2 `node_modules/next/dist/docs/`；其 `error.md` 记录 `retry` 已在 16.3 稳定。
- 本地 UI UX Pro Max 目录/平面布局检索与 React Best Practices；采用服务端外壳、最小序列化、直接派生筛选结果。
- [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md)：针对实现进行界面审查，不把有限审查称为完整无障碍认证。
- [MCP 官方介绍](https://modelcontextprotocol.io/docs/2026-07-28/getting-started/intro)：仅核对案例中的协议术语，虚构连接器不代表真实项目或已运行服务。
