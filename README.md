# MallAgent

MallAgent 是一个面向电商售后场景的完整源码项目。它在开源 `mall` 商城基础上集成了 Vue 管理端和 Python 智能客服 Agent，可完成订单查询、物流查询、退换货申请、售后进度跟踪、RAG 知识检索和多轮会话。

本仓库推荐的本地部署方式是：**Java、Vue、Python 应用在 Windows 本机运行，Docker Desktop 只运行数据库、中间件和向量库。**

## 项目组成

| 目录 | 作用 | 主要技术 |
| --- | --- | --- |
| `mall/` | 商城后台、搜索服务和门户 API | Java 17、Spring Boot 3.5、MyBatis |
| `mall-admin-web/` | 商城后台管理页面及 Agent 入口 | Vue 3、Vite 7、Element Plus |
| `after_sales_agent/` | 售后智能客服、RAG、记忆和商城工具调用 | Python 3.13、FastAPI、LangGraph、Milvus |
| `ops/vm-dependencies/` | 本地开发所需的统一基础设施 | Docker Compose |

`migrations/`、`scripts/` 和 `tests/` 是完整源码仓库的一部分，分别用于数据库演进、运维/数据导入和自动化测试，不应删除。

## 整体架构

```mermaid
flowchart LR
    Browser["浏览器"] --> Web["mall-admin-web :5173"]
    Web --> Admin["mall-admin :8080"]
    Web --> Agent["after-sales-agent :8000"]
    Agent --> Portal["mall-portal :8085"]
    Search["mall-search :8081"] --> MySQL[(MySQL)]
    Search --> ES[(Elasticsearch + IK)]
    Admin --> MySQL
    Admin --> Redis[(Redis 8)]
    Portal --> MySQL
    Portal --> Redis
    Portal --> Mongo[(MongoDB)]
    Portal --> Rabbit[(RabbitMQ)]
    Agent --> Redis
    Agent --> PostgreSQL[(PostgreSQL)]
    Agent --> Milvus[(Milvus)]
    Milvus --> etcd[(etcd)]
    Milvus --> MinIO[(MinIO)]
```

## 环境要求

| 工具 | 要求 | 说明 |
| --- | --- | --- |
| Windows | 10/11，64 位 | 本手册命令使用 PowerShell |
| Docker Desktop | 支持 Compose V2 | 建议为 Docker 分配至少 8 GB 内存 |
| JDK | 17 | `mall/pom.xml` 指定 Java 17 |
| Maven | 3.9+ | 用于构建 Java 多模块项目 |
| Node.js | `^20.19.0` 或 `>=22.12.0` | 以 `mall-admin-web/package.json` 为准 |
| Python | 3.13+ | 以 `after_sales_agent/pyproject.toml` 为准 |
| Git | 2.40+ | 用于克隆和更新仓库 |

先检查命令是否可用：

```powershell
git --version
docker --version
docker compose version
java -version
mvn -version
node --version
cmd /c npm --version
python --version
```

如果 PowerShell 禁止执行 `npm.ps1`，后续直接使用 `cmd /c npm ...`，不必修改系统执行策略。

## 端口和本地凭据

| 服务 | 本机端口/地址 | 本地开发凭据 |
| --- | --- | --- |
| MySQL | `3306` | `root / 123456`，数据库 `mall` |
| Redis | `6379`、`6380` | 密码 `123456`，两个端口指向同一实例 |
| PostgreSQL | `5434` | `mall_agent / 123456`，数据库 `mall_agent` |
| MongoDB | `27017` | `root / 123456`，认证库 `admin` |
| RabbitMQ | `5672`、管理页 `15672` | `root / 123456`，虚拟主机 `/mall` |
| Elasticsearch | `9200` | 本地开发关闭安全认证 |
| MinIO | API `9000`、控制台 `9001` | `minioadmin / minioadmin` |
| Milvus | SDK `19530`、WebUI `9091` | 本地开发无令牌 |
| mall-admin | `8080` | 商城管理员 `admin / macro123` |
| mall-search | `8081` | 无独立登录页 |
| mall-portal | `8085` | 商城会员 API |
| After-sales Agent | `8000` | 通过商城会员身份建立会话 |
| mall-admin-web | `5173` | 使用商城管理员账号登录 |

> 上述密码只用于本机开发。部署到服务器前必须修改 Compose、Java 配置和 Agent `.env` 中的密码，并启用 Elasticsearch、MinIO、Milvus 等服务的认证。

## 一、获取源码

```powershell
git clone https://github.com/Rikka1008/MallAgent.git
cd MallAgent
```

如果已经克隆过：

```powershell
git pull --ff-only
```

## 二、启动基础设施

进入统一 Compose 目录：

```powershell
cd ops\vm-dependencies
docker compose build elasticsearch
docker compose up -d
docker compose ps
```

首次启动会下载多个镜像，并在构建 Elasticsearch 镜像时安装与 `8.18.1` 完全匹配的 IK 中文分词插件。Milvus 首次就绪通常比其他容器慢。

查看状态和日志：

```powershell
docker compose ps
docker compose logs -f mysql
docker compose logs -f elasticsearch
docker compose logs -f milvus
```

所有容器显示 `running` 或 `healthy` 后再启动应用。可用以下命令快速检查关键服务：

```powershell
docker compose exec mysql mysqladmin ping -uroot -p123456
docker compose exec redis redis-cli -a 123456 ping
docker compose exec postgres pg_isready -U mall_agent -d mall_agent
Invoke-RestMethod http://localhost:9200
Invoke-RestMethod http://localhost:9091/healthz
```

### MySQL 首次初始化

Compose 会在 **MySQL 数据卷为空时** 自动按顺序执行：

1. `mall/document/sql/mall.sql`：商城表结构和基础数据；
2. `mall/document/sql/20260714_after_sales_apply.sql`：售后字段与索引；
3. `mall/document/sql/mall_agent_seed.sql`：Agent 联调用订单和售后数据。

确认初始化完成：

```powershell
docker compose exec mysql mysql -uroot -p123456 -D mall -e "SHOW TABLES;"
```

如果之前已经创建过 `mysql-data` 卷，入口脚本不会重复运行。开发环境确实允许清空全部基础设施数据时，可执行：

```powershell
docker compose down -v
docker compose up -d
```

`down -v` 会永久删除本项目所有 Docker 命名卷，包括 MySQL、PostgreSQL、MongoDB、Milvus 和 MinIO 数据；有数据时不要执行。

### 创建 MinIO 存储桶

打开 [http://localhost:9001](http://localhost:9001)，使用 `minioadmin / minioadmin` 登录，创建名为 `mall` 的 Bucket。商城后台的 MinIO 上传配置默认使用该名称。

完成后回到仓库根目录：

```powershell
cd ..\..
```

## 三、构建并启动 Java 服务

构建整个 Maven 多模块项目：

```powershell
cd mall
mvn clean package -DskipTests
```

构建成功后，分别打开三个 PowerShell 窗口，从 `mall` 目录启动：

```powershell
java -jar mall-admin\target\mall-admin-1.0-SNAPSHOT.jar
```

```powershell
java -jar mall-search\target\mall-search-1.0-SNAPSHOT.jar
```

```powershell
java -jar mall-portal\target\mall-portal-1.0-SNAPSHOT.jar
```

当前 `dev` 配置已与统一 Compose 对齐：MySQL、Redis、MongoDB 和 RabbitMQ 均连接 `localhost`。服务启动后检查：

- mall-admin Swagger：[http://localhost:8080/swagger-ui.html](http://localhost:8080/swagger-ui.html)
- mall-search Swagger：[http://localhost:8081/swagger-ui.html](http://localhost:8081/swagger-ui.html)
- mall-portal Swagger：[http://localhost:8085/swagger-ui.html](http://localhost:8085/swagger-ui.html)

首次使用搜索功能前，将 MySQL 商品导入 Elasticsearch：

```powershell
Invoke-RestMethod -Method Post http://localhost:8081/esProduct/importAll
```

如果返回成功并显示导入数量，说明 MySQL、Elasticsearch 和 IK 插件均已连通。

## 四、配置并启动售后 Agent

回到仓库根目录并进入 Agent：

```powershell
cd ..\after_sales_agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

编辑 `after_sales_agent/.env`，至少填写真实的模型配置：

```dotenv
LLM_MODEL_NAME=你的模型名称
LLM_BASE_URL=模型服务的兼容 API 地址
LLM_API_KEY=你的 API Key
```

仓库只提交 `.env.example`，真实 `.env` 已被根 `.gitignore` 忽略。默认基础设施连接为：

```dotenv
REDIS_URL=redis://:123456@localhost:6380/0
DATABASE_URL=postgresql+asyncpg://mall_agent:123456@localhost:5434/mall_agent
MILVUS_URI=http://localhost:19530
MALL_PORTAL_BASE_URL=http://localhost:8085
MALL_ADMIN_BASE_URL=http://localhost:8080
```

执行 PostgreSQL 迁移：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### 导入 RAG 知识库

Agent 默认使用 `BAAI/bge-m3`。如果本机尚未缓存该模型，先把 `.env` 中下面两项设为 `0`，允许首次联网下载：

```dotenv
HF_HUB_OFFLINE=0
TRANSFORMERS_OFFLINE=0
```

然后执行：

```powershell
.\.venv\Scripts\python.exe scripts\ingest_rag_sources.py
```

模型和知识数据准备完毕后，可把两个离线开关改回 `1`。模型下载占用较多磁盘和内存；内存紧张时可降低 `EMBEDDING_BATCH_SIZE`。

启动 Agent：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

检查接口：

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready
```

- `/health` 和 `/health/live` 用于进程存活检查；
- `/health/ready` 会检查模型、Redis、Milvus 和商城连接，依赖未准备好时会返回 `503`；
- Agent 演示页：[http://localhost:8000](http://localhost:8000)。

## 五、启动 Vue 管理端

再打开一个 PowerShell 窗口：

```powershell
cd mall-admin-web
cmd /c npm ci
cmd /c npm run dev
```

打开 [http://localhost:5173](http://localhost:5173)，使用 `admin / macro123` 登录。开发配置会把商城后台请求发往 `http://localhost:8080`，把 `/agent-api` 代理到 `http://localhost:8000`。

生成生产静态文件：

```powershell
cmd /c npm run type-check
cmd /c npm run build-only
```

产物位于 `mall-admin-web/dist/`，该目录可重新生成，因此不会提交到 Git。

## 六、联调验收

建议按以下顺序检查：

1. `docker compose ps` 中基础设施均已运行；
2. 三个 Java Swagger 页面可以打开；
3. `POST /esProduct/importAll` 成功导入商品；
4. Agent `/health/live` 返回 `ok`，`/health/ready` 所有依赖为 `ok`；
5. Vue 管理端可以用 `admin / macro123` 登录；
6. 售后对话能够读取商城会员身份并查询 `ORD1001`、`ORD1002` 等联调订单；
7. RabbitMQ 管理页 [http://localhost:15672](http://localhost:15672)、MinIO 控制台 [http://localhost:9001](http://localhost:9001) 和 Milvus WebUI [http://localhost:9091/webui/](http://localhost:9091/webui/) 可以打开。

## 七、测试命令

Java：

```powershell
cd mall
mvn test -DskipTests=false
```

Python：

```powershell
cd after_sales_agent
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests scripts
```

Vue：

```powershell
cd mall-admin-web
cmd /c npm run type-check
cmd /c npm run build-only
```

## 八、停止和重启

停止应用时，在各 Java、Python、Vite 窗口按 `Ctrl+C`。

停止基础设施但保留数据：

```powershell
cd ops\vm-dependencies
docker compose stop
```

重新启动：

```powershell
docker compose start
```

删除容器但保留命名卷：

```powershell
docker compose down
```

## 常见问题

### 端口被占用

```powershell
Get-NetTCPConnection -LocalPort 3306,6379,6380,5434,8080,8081,8085,8000,5173,9200,19530 -ErrorAction SilentlyContinue
```

停止冲突程序，或同时修改 Compose 端口和对应应用配置。只改一侧会导致连接失败。

### MySQL 有容器但没有表

通常是旧 `mysql-data` 卷已存在，导致初始化脚本被跳过。先查看 `docker compose logs mysql`；只有确认数据可删除时才使用 `docker compose down -v` 重新初始化。

### mall-search 报 `ik_max_word` 不存在

IK 插件版本必须与 Elasticsearch `8.18.1` 完全一致。重新执行：

```powershell
docker compose build --no-cache elasticsearch
docker compose up -d --force-recreate elasticsearch
```

不要直接把 Elasticsearch 升级到其他版本而不同时更新 IK 插件和 Spring Data Elasticsearch 兼容性。

### Agent 就绪检查返回 503

查看返回 JSON 中具体失败项，并依次确认：

```powershell
docker compose ps
python scripts\smoke_test_services.py
```

常见原因包括 `.env` 中模型密钥无效、Redis 密码不一致、尚未执行 Alembic、Milvus 仍在启动或商城 API 未启动。

### BGE-M3 模型无法加载

首次下载时将 `HF_HUB_OFFLINE` 和 `TRANSFORMERS_OFFLINE` 设为 `0`；确认下载完成后再启用离线模式。企业网络使用代理时，需要让 Python/Hugging Face 能访问模型源。

### Docker Desktop 内存不足

Elasticsearch、Milvus、MySQL 和模型同时运行会占用较多内存。建议为 Docker Desktop 分配至少 8 GB；资源有限时可先只启动所需服务，例如：

```powershell
docker compose up -d mysql redis postgres mongodb rabbitmq minio etcd milvus
```

## 仓库安全与提交规范

- 不提交 `after_sales_agent/.env`、模型密钥、Cookie、JWT 或数据库备份；
- 不提交 `logs/`、`.ruff_cache/`、`.pytest_cache/`、`node_modules/`、`target/`、`dist/`、`build/`；
- `migrations/`、`scripts/`、`tests/`、SQL 和 RAG 原始数据属于源码，应保留；
- 本地开发默认密码不可直接用于公网或生产环境；
- 对外部署必须增加 TLS、网络访问控制、最小权限账号、密钥管理和数据备份。

## 子项目文档

- [mall 商城说明](mall/README.md)
- [Vue 管理端说明](mall-admin-web/README.md)
- [统一基础设施 Compose](ops/vm-dependencies/docker-compose.yml)
- [Agent 环境变量示例](after_sales_agent/.env.example)
- [商城数据库脚本](mall/document/sql/)
- [Agent PostgreSQL 迁移](after_sales_agent/migrations/)
- [Agent 运维与导入脚本](after_sales_agent/scripts/)
- [Agent 自动化测试](after_sales_agent/tests/)

## 许可证与上游来源

`mall/` 和 `mall-admin-web/` 基于 macrozheng 的 mall 开源项目演进；使用或再发布时请同时遵守各子项目中的许可证与署名要求。本仓库新增的 Agent、部署配置和业务扩展也应在发布前完成许可证核对。
