# AgentRadar

面向 AI 初学者、产品运营人员和企业技术支持团队的 AI 工具发现与应用平台。
当前阶段为 **P01 产品规划与页面原型**：发现、详情与固定选型演示，保留 P00 的真实工程健康检查。
工具均为明确标识的虚构案例，没有真实采集、模型、用户系统或业务数据写入。

产品定义见 [PRD](docs/product/prd.md)；配套文档为
[用户画像](docs/product/personas.md)、[用户旅程](docs/product/user-journeys.md)、
[功能优先级](docs/product/feature-priority.md)、[信息架构](docs/product/information-architecture.md)、
[设计规范](docs/product/design-system.md) 和 [指标字典](docs/product/metrics.md)。

## 前置条件

- Docker Desktop：运行中、切换到 Linux 容器，提供 Docker Compose v2 或更新版本。
- Git。仅使用容器启动时不需要在宿主机安装 Python、Node.js。
- 本地开发/检查：Python **3.12**、Node.js **24** 与 npm。
- 本机 3000、8000、15432 端口可用；首次安装/构建需要访问包仓库和容器镜像仓库。

后端直接依赖在 `apps/api/requirements.in`，完整固定版本在 `requirements.lock`；
开发依赖使用 `requirements-dev.in` 和 `requirements-dev.lock`。
前端依赖在 `apps/web/package.json` 和 `package-lock.json`，安装使用 `npm ci`。
不需要安装全局 npm/pip 包。

## 从零启动（Windows PowerShell）

以下命令均从项目根目录执行。使用自己的实际目录替换第一行：

```powershell
Set-Location D:\Pycharmpjc\githubradar
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker version
docker compose version
docker compose up -d --build --wait
docker compose ps -a
```

首次启动会依次等待 PostgreSQL 就绪、执行 Alembic 基线迁移、启动 API、启动前端。
迁移容器 `migrate` 显示 `Exited (0)` 是正常结果；其他三个服务应为 healthy。

打开：

- 产品入口/发现页：<http://localhost:3000/discover>（根地址自动转入）。
- 示例详情：<http://localhost:3000/tools/knowledge-base>。
- 选型演示：<http://localhost:3000/assistant>。
- 工程状态：<http://localhost:3000/status>（P00 健康页面迁至此处）。
- 健康 API：<http://localhost:8000/api/v1/health>
- API 文档：<http://localhost:8000/api/v1/docs>

工程状态页面应显示“全部正常”、后端“已连接”、数据库“正常”、检查时间和请求 ID。
点击“重新检查”会执行新的真实 API 请求；重新检查期间显示“检查中…”。

## P01 原型走查

1. 进入发现页，搜索“知识库”，选择“知识管理”和“无需代码（示例设定）”，点击“搜索与筛选”。
2. 打开“团队知识库问答助手”，查看适用、不适用、条件和来源边界。
3. 点击“用这个场景试试选型助手”，输入至少 10 个非空白字符的任务，选择场景与技术条件。
4. 点击“展示演示方案”，查看固定规则、候选与待核实项；可修改需求或回详情。
5. 搜索不存在的词验证空结果；清除筛选恢复目录；顶部“工程状态”仍验证真实 API/数据库。

三页始终标明“演示数据”。助手另外显示“演示交互，未连接模型”；文本不参加语义分析。
数据唯一文件为 `apps/web/public/demo/catalog.json`，通过静态文件读取，不是后端业务接口。
目录请求有 5 秒超时、格式检查和手动重试。需求与结果仅在页面内存，刷新或离开即清除，不提交到业务服务。
其他产品/运营/企业路由仅在信息架构中规划，不提供不可用导航；直接访问会显示未找到和返回入口。

## 配置与访问地址

根目录 `.env.example` 只包含本地开发示例凭据，复制后的 `.env` 被 Git 与镜像构建忽略。
不要把示例凭据用于公开部署；不要在 `NEXT_PUBLIC_*` 中存放任何密钥。

| 配置 | 作用 |
| --- | --- |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Compose 数据库初始化及容器 API 连接 |
| `POSTGRES_PORT` | 数据库宿主机映射端口，默认 15432，容器内部保持 5432 |
| `DATABASE_URL` | 在宿主机运行 API / Alembic 的 PostgreSQL 连接地址 |
| `DATABASE_TIMEOUT_SECONDS` | 健康检查总超时，默认 3 秒；同时设置连接、连接池和语句超时 |
| `CORS_ORIGINS` | 允许的浏览器 Origin，JSON 数组，默认 localhost/127.0.0.1:3000 |
| `LOG_LEVEL` | API 应用日志级别，默认 INFO |
| `NEXT_PUBLIC_API_BASE_URL` | 浏览器访问的 API 根地址；在前端构建时固定 |

| 访问方 | 前端 | API | PostgreSQL |
| --- | --- | --- | --- |
| 浏览器/宿主机 | `http://localhost:3000` | `http://localhost:8000` | `127.0.0.1:15432` |
| Compose 容器 | `http://web:3000` | `http://api:8000` | `db:5432` |

Compose 根据 `POSTGRES_*` 构造容器内数据库 URL；本机运行则使用 `DATABASE_URL`。
本阶段使用 URL 安全字符组成的开发凭据；修改这些凭据时须同步本机 URL。
如果密码包含 `@`、`:`、`/` 等保留字符，需要 URL 编码，不能直接拼入连接 URL。
容器端当前拼接方式的限制见阶段基线文档。

修改公开 API 地址后需要重新构建前端：

```powershell
docker compose up -d --build web
```

PostgreSQL 数据存储在 Compose 命名卷 `agentradar_postgres_data`。
普通停止和移除容器会保留数据卷；本文不提供删除数据卷的命令。
已初始化的数据卷不会因为修改 `POSTGRES_PASSWORD` 自动更改数据库密码。

## 迁移

P00 没有业务实体，基线迁移 `0001_p00_baseline` 的 upgrade/downgrade 为空。
执行迁移仍会创建 `alembic_version` 并记录当前版本，不创建虚构业务表。

```powershell
# 完整启动时自动迁移；单独执行或检查时使用：
docker compose run --rm migrate
docker compose exec api python -m alembic -c alembic.ini current
docker compose exec db psql -U agentradar -d agentradar -c 'SELECT version_num FROM alembic_version;'
```

后续模型变化必须新增并审查 Alembic 迁移，不使用 `create_all()` 替代迁移。

## 安装本地检查依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements-dev.lock
npm.cmd --prefix apps/web ci --ignore-scripts
```

不需要激活虚拟环境；显式解释器路径也能避免 PowerShell 执行策略问题。
`npm.cmd` 可避免 `npm.ps1` 被执行策略阻止。

有明确依赖变更时，更新输入文件后重新生成并审查锁文件：

```powershell
.\.venv\Scripts\python.exe -m piptools compile --allow-unsafe --strip-extras --output-file apps/api/requirements.lock apps/api/requirements.in
.\.venv\Scripts\python.exe -m piptools compile --allow-unsafe --strip-extras --output-file apps/api/requirements-dev.lock apps/api/requirements-dev.in
```

开发锁约束到运行锁，避免同一后端依赖在开发和容器中使用不同版本。

## 自动化检查

```powershell
.\.venv\Scripts\python.exe -m ruff check --config apps/api/pyproject.toml apps/api tests
.\.venv\Scripts\python.exe -m ruff format --check --config apps/api/pyproject.toml apps/api tests
.\.venv\Scripts\python.exe -m pytest -c apps/api/pyproject.toml apps/api/tests -m "not integration"
npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run typecheck
npm.cmd --prefix apps/web run build
```

单元测试使用明确标记的数据库会话替身，验证状态码、统一错误、安全输出、超时、CORS 和请求 ID。
它们不能证明真实 PostgreSQL 可用。

真实数据库集成验证（先启动 Compose 数据库）：

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://agentradar:agentradar_dev_only@127.0.0.1:15432/agentradar'
.\.venv\Scripts\python.exe -m pytest -c apps/api/pyproject.toml apps/api/tests -m integration
```

集成测试使用 PostgreSQL，执行并重复执行迁移、读取迁移版本、验证真实 SQL 查询及真实连接失败。
未设置 `TEST_DATABASE_URL` 时会明确跳过；跳过不等于通过。后续有业务数据时应使用独立测试数据库。

浏览器验证（使用已安装的 Microsoft Edge）：

```powershell
$env:PLAYWRIGHT_CHANNEL = 'msedge'
$env:HEALTH_SCENARIO = 'healthy'
.\.venv\Scripts\python.exe -m pytest -c apps/api/pyproject.toml tests/e2e -m e2e
```

也可在项目内下载 Chromium，不安装系统或全局依赖：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.cache\ms-playwright"
.\.venv\Scripts\python.exe -m playwright install chromium
Remove-Item Env:PLAYWRIGHT_CHANNEL -ErrorAction SilentlyContinue
```

以上 `Remove-Item Env:` 仅清除当前 PowerShell 会话变量，不删除文件。
浏览器测试只访问真实服务，截图保存在被 Git 忽略的 `artifacts/`。
P00 健康测试访问 `/status`；P01 访问真实页面和静态演示文件，覆盖三种宽度、键盘流程、查询 URL、
表单与错误恢复。空目录/损坏响应使用明确的响应替身，网络失败使用请求中断；都不算真实业务数据验证。

## 手工和浏览器故障验收

请只在本机开发环境操作，以下停止操作均可恢复，不清除数据。

1. 正常：打开 `/status` 页面，点击重新检查，确认状态、时间和请求 ID 更新。
2. 数据库异常：执行 `docker compose stop db`，重新检查，页面应显示“数据库异常”，
   后端“已连接”，数据库“异常”；API 返回 HTTP 503 和 `DATABASE_UNAVAILABLE`。
3. 恢复数据库：执行 `docker compose start db`，待数据库就绪后重新检查，应恢复正常。
4. 后端不可达：执行 `docker compose stop api`，重新检查，页面应显示“无法连接后端”，
   数据库显示“未知”；执行 `docker compose start api` 后可恢复。

对应自动化命令：

```powershell
docker compose stop db
$env:HEALTH_SCENARIO = 'database_unhealthy'
.\.venv\Scripts\python.exe -m pytest -c apps/api/pyproject.toml tests/e2e/test_health_page.py -m e2e
docker compose start db
# 等待数据库就绪，再测试下一项。
docker compose stop api
$env:HEALTH_SCENARIO = 'unreachable'
.\.venv\Scripts\python.exe -m pytest -c apps/api/pyproject.toml tests/e2e/test_health_page.py -m e2e
docker compose start api
$env:HEALTH_SCENARIO = 'healthy'
```

应用健康检查不重试 SQL，以免放大故障和延长请求时间；前端可手动重试。

## 宿主机开发（可选）

只启动数据库，并在根目录执行迁移、启动后端：

```powershell
docker compose up -d db --wait
.\.venv\Scripts\python.exe -m alembic -c apps/api/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir apps/api --loop app.core.event_loop:selector_loop_factory --host 127.0.0.1 --port 8000 --reload --no-access-log
```

另开一个 PowerShell，从根目录启动前端：

```powershell
$env:NEXT_PUBLIC_API_BASE_URL = 'http://localhost:8000'
npm.cmd --prefix apps/web run dev
```

不要同时启动占用相同端口的容器 API/前端和本机开发服务器。
Windows 上 psycopg 异步连接要求 Selector 事件循环，因此不要省略上面的 `--loop` 参数。
数据库地址显式使用 `127.0.0.1`，与容器的 IPv4 端口绑定保持一致，避免本机 IPv6 回退等待。

## 日志、停止与排查

```powershell
docker compose logs --tail 100 api
docker compose logs --tail 100 migrate db web
Invoke-RestMethod http://localhost:8000/api/v1/health
docker compose stop
# 停止并移除本项目容器与网络，保留数据库命名卷：
docker compose down
```

- Docker 无法连接：确认 Docker Desktop 已运行且使用 Linux 容器，执行 `docker info`。
- 端口占用：用 `Get-NetTCPConnection -LocalPort 3000,8000,15432` 检查，不要随意结束其他程序。
- 页面请求失败：检查 API、浏览器 Network 面板及 CORS Origin；不要把 `http://api:8000` 配给浏览器。
- API 返回 503：检查数据库健康、迁移日志、连接地址及已有卷的凭据，使用请求 ID 关联 API JSON 日志。
- 修改环境后无变化：容器运行变量需重新创建容器；`NEXT_PUBLIC_*` 需要重新构建前端。
- 依赖/镜像下载失败：检查网络连接后重试原命令，不关闭校验或强制升级依赖。
- PowerShell 5.1 的 `curl` 可能是 `Invoke-WebRequest` 别名；需要原生 curl 时写 `curl.exe`。
  API 返回 503 时 `Invoke-RestMethod` 会抛出异常，这是预期 HTTP 行为。

Linux/macOS：使用 `.venv/bin/python` 替换 `.venv\Scripts\python.exe`，使用 `npm` 替换 `npm.cmd`，
使用 `cp .env.example .env` 复制初始配置；临时变量写为
`TEST_DATABASE_URL='...' .venv/bin/python -m pytest ...`，Docker 命令相同。

## CI、阶段基线与 Git

GitHub Actions 配置包含后端 Ruff/Pytest、真实 PostgreSQL 迁移与集成测试、前端静态检查/类型检查/构建，
以及 Compose + Playwright 的原型流程与真实健康链路验证。正常场景运行整个 `tests/e2e`，
停止数据库/API 的故障场景只运行健康测试文件。实际本地执行结果和已知限制见
[P01 基线](docs/architecture/p01-baseline.md) 与历史 [P00 基线](docs/architecture/p00-baseline.md)。
未在 GitHub 运行的工作流不能宣称远端通过。

当前默认分支为 `main`。P00 已验收提交并推送；P01 完成后先等待用户验收，只有明确验收通过后才创建本地提交。
创建远程仓库、推送或改写历史必须另行获得明确指令。
