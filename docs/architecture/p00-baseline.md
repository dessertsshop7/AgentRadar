# AgentRadar P00 工程基线

阶段日期：2026-10-16（Asia/Singapore）。当前为 P00，验收前不创建本地 Git 提交。

## 范围与结构

采用 Next.js + TypeScript 前端、FastAPI + Pydantic 后端、SQLAlchemy + psycopg 数据访问、
Alembic 迁移与 PostgreSQL 17。前后端独立依赖，单一数据库，后端按实际职责组织为模块化单体。
没有业务实体、用户、采集、AI 模型调用、调度任务、搜索、消息队列或微服务。

目录职责及完整命令见根目录 AGENTS.md、README.md。主要交付为：

- `apps/web/app`：服务端页面外壳与客户端健康状态组件。
- `apps/api/app/core`：环境变量校验、错误响应和 JSON 日志。
- `apps/api/app/api`：版本化健康路由与 Pydantic 响应模型。
- `apps/api/app/db`：异步引擎与请求级会话。
- `apps/api/alembic`：空基线迁移和后续迁移生成模板。
- `apps/api/tests`：单元测试及真实 PostgreSQL 集成验证。
- `tests/e2e`：真实服务浏览器验证。
- `infra`、`compose.yaml`、`.github/workflows/ci.yml`：容器与持续集成。

## 请求链路与契约

浏览器 `http://localhost:3000` → `http://localhost:8000/api/v1/health` → PostgreSQL。
浏览器直接调用 API，以验收真实访问地址与 CORS；不通过 Next.js 代理掩盖跨域配置。
容器内 API 使用 `db:5432`；宿主机使用 `127.0.0.1:15432`。
本机已有服务占用 5432，因此改用 15432 映射，不修改或停止已有服务。
宿主机 DSN 显式使用 IPv4，避免 `localhost` 首先解析为 `::1` 造成连接回退等待。

健康响应：

```json
{
  "status": "ok",
  "dependencies": {"database": {"status": "healthy"}},
  "request_id": "<UUID 或经过校验的客户端请求 ID>"
}
```

数据库不可用时返回 **HTTP 503**：

```json
{
  "status": "degraded",
  "dependencies": {"database": {"status": "unhealthy"}},
  "request_id": "<同响应头 X-Request-ID>",
  "error": {"code": "DATABASE_UNAVAILABLE", "message": "数据库暂时不可用，请稍后重试。"}
}
```

其他错误使用 `{"error":{"code":"...","message":"..."},"request_id":"..."}`。
输入校验为 `VALIDATION_ERROR` / 422，未处理内部错误为 `INTERNAL_ERROR` / 500，
HTTP 错误为 `HTTP_<状态码>`。不向客户端返回连接字符串、密码、原始输入或内部异常堆栈。
CORS 拒绝预检使用 `CORS_REJECTED` / 400 和相同错误结构。
测试专用校验/崩溃路由仅由测试 fixture 注册，不进入正式应用。

每个请求生成 UUID；仅接受 1–64 位字母、数字、`.`、`_`、`-` 组成的传入 `X-Request-ID`。
响应头、健康/错误响应体和 JSON 请求完成日志使用同一 ID。CORS 预检也有请求 ID。
日志只记录方法、路径、状态码、耗时和异常类型，不记录查询参数、请求体、凭据或堆栈。

健康检查实际执行 `SELECT 1`；默认总超时 3 秒，且限制连接池等待、驱动连接和服务端语句时间。
总超时涵盖连接获取与 SQL 执行，不进行自动 SQL 重试。SQLAlchemy 使用有界连接池和连接预检，
会话随请求释放，引擎随应用关闭释放。
会话不自动提交；后续写操作需要显式管理事务。
Windows 的默认 Proactor 事件循环与 psycopg 不兼容，Uvicorn 使用显式 Selector 循环工厂，
真实集成测试也显式使用 Selector，不修改全局事件循环策略。

## 配置、镜像与迁移

根 `.env.example` 是开发配置样例；真实 `.env` 不进入 Git 或 Docker 构建上下文。
Python 使用 Pydantic Settings；环境变量优先于 `.env`。
`DATABASE_URL` 使用 `SecretStr`，仅接受 `postgresql+psycopg` 驱动。

前端公开 API 地址在构建时写入；不得包含秘密，变更后需要重新构建。
CORS 明确列出 localhost 与 127.0.0.1 的开发 Origin，不默认允许任意来源。

数据库使用持久化命名卷。启动顺序：db healthy → migrate 成功退出 → api healthy → web。
API 与 web 镜像分别用独立非 root 用户运行；不复制真实配置文件。

基线迁移 `0001_p00_baseline` 没有业务表变化，仅由 Alembic 创建并记录 `alembic_version`。
重复执行 `upgrade head` 应安全；未来表结构变更必须新增迁移，不用 `create_all()`。
PostgreSQL 集成测试会升级目标数据库，后续存在业务数据时必须改用独立测试数据库。

## 测试分层与运行

- 单元：以明确标记的会话替身触发健康、数据库错误、慢查询，验证 HTTP 契约、总超时、
  日志关联、统一错误、CORS 和请求 ID 校验；这些结果不是数据库连通证据。
- 集成：`TEST_DATABASE_URL` 指向真实 PostgreSQL，验证迁移版本、重复迁移、真实查询、真实连接失败。
  没有配置时明确 skip，不用 SQLite 或 Mock 替代。
- 浏览器：Playwright 使用真实页面/API；通过停止本项目 db/api 验证异常状态，不伪造响应。
  检查手动重试、请求 ID、检查时间及 375px 窄屏。
- 前端：ESLint、Next 类型生成 + TypeScript、生产构建。
- CI：分别运行后端 + PostgreSQL、前端、Compose + Playwright 作业。

全部复现命令在 README。验收记录只记录实际运行的检查，不把配置完成当作检查通过。

## 本轮验证记录

本地实现完成，等待用户阶段验收。未创建 Git 提交、远程仓库或推送。

| 检查 | 实际结果 |
| --- | --- |
| Git / 忽略规则 | main 分支，无提交；`.env`、依赖、缓存、构建产物与个人 `.agents` 均被忽略 |
| 后端 TDD 起点 | 空实现下观察到 14 项预期失败；统一 CORS 拒绝错误也先观察失败再修复 |
| Ruff check / format check | 通过，20 个 Python 文件符合格式要求 |
| Pytest 后端完整套件 | **19 passed**：16 项单元测试、3 项真实 PostgreSQL 集成测试；无跳过 |
| Python 依赖一致性 | `pip check` 通过，无损坏依赖 |
| 前端 ESLint / TypeScript | 通过；类型检查先执行 `next typegen` |
| Next.js 生产构建 | Windows 宿主机与 Linux Docker 镜像构建均通过 |
| npm 审计 | 最终完整安装审计与生产依赖审计均为 0 vulnerabilities |
| Compose | `docker compose up -d --build --wait` 成功，web/api/db 均 healthy，migrate Exited (0) |
| Alembic | 宿主机与容器均执行成功；数据库记录 `0001_p00_baseline`，重复迁移通过 |
| 真实浏览器正常场景 | Compose 环境下 Playwright **2 passed**，验证页面、响应、请求 ID、手动刷新、375px 与加载态 |
| 真实浏览器数据库故障 | 停止本项目 db 后 **2 passed**；真实 HTTP 503，后端已连接、数据库异常；恢复后 API 回到 200 |
| 真实浏览器 API 故障 | 停止本项目 api 后 **2 passed**；后端不可访问、数据库未知；验证后已恢复服务 |
| 容器运行用户 / 配置文件 | API UID 10001、web UID 1000；运行镜像均不存在 `/app/.env` |
| GitHub Actions | 已完成三个作业的配置与本地命令验证；**没有远端运行记录，不能宣称 CI 已通过** |

浏览器使用本机已安装的 Microsoft Edge，所有健康响应来自真实 API。
加载态测试仅暂缓并继续真实请求，不伪造响应；数据库/API 故障由真实停止本项目容器触发。
正常及异常页面截图位于本机 `artifacts/health-*.png`，已人工检查正常桌面和数据库异常窄屏截图。
这些截图被 Git 忽略，不是产品内的 Mock 数据。

后端测试实际产生 1 条上游 `StarletteDeprecationWarning`：当前 TestClient 提示后续应由 httpx
迁移至 httpx2。测试仍执行成功，未隐藏警告；本阶段没有为消除警告再更换测试客户端。

本地验收条件：真实 SQL 的正常/503、受限超时、错误约定、日志关联、四类 UI 状态、
迁移、全栈启动、静态检查及生产构建均已验证。CI 配置已交付，远端执行需后续经授权推送后验证。

## 依赖取舍与已知限制

- 前端使用 ESLint 10 + TypeScript ESLint 推荐规则。Next 官方 ESLint 预设的 glob 依赖链
  在本轮安装审计中报告高危告警，且其插件 peer 依赖仍限制 ESLint 9；因此未采用该预设。
  当前没有 Next 专属、React Hooks 专属 lint 规则，依靠类型检查与浏览器行为测试覆盖本阶段。
- 后端固定完整解析版本，暂未附加发行包哈希。最初的全平台哈希生成实际下载发行包时超时；
  不为此绕过 TLS 或关闭包校验。后续可在网络稳定的环境补充哈希。
- Docker 基础镜像固定为已实际拉取验证的 Python 3.12、Node 24、PostgreSQL 17 系列和 digest。
- Compose 的容器数据库 URL 当前由 `POSTGRES_*` 拼接，开发凭据需使用 URL 安全字符；
  含保留字符的真实密码不能直接套用该拼接方式。公开部署前需改为安全的独立配置方案。
- 只提供本机开发环境，端口绑定回环地址；尚无认证、TLS 或生产部署方案。
- 状态反映最近一次主动检查，不是持续监控，也不提供生产可用性保证。
- 远端 GitHub Actions 是否成功，必须以实际工作流运行结果为准。

## 官方参考

- [Next.js 安装与检查命令](https://nextjs.org/docs/app/getting-started/installation)
- [FastAPI 错误处理](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- [SQLAlchemy psycopg 驱动](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#psycopg)
- [Compose 启动依赖](https://docs.docker.com/compose/how-tos/startup-order/)
- [psycopg 异步连接与 Windows 约束](https://www.psycopg.org/psycopg3/docs/advanced/async.html)

实现前也阅读了已安装 Next.js 16.4.2 的 `node_modules/next/dist/docs/`，以核对客户端边界及配置。
