# Network RAG

面向网络工程知识库的全栈 RAG 应用。管理员可以上传并索引技术文档，普通用户可以基于已索引内容进行带引用来源的流式问答。

## 功能

- 基于 Argon2、JWT 和 HttpOnly Cookie 的用户认证
- 管理员用户管理和角色权限控制
- PDF、DOCX、Markdown、TXT 文档上传与解析
- 文档切块和 SentenceTransformer Embedding
- Qdrant 向量检索、jieba 分词的 SQLite FTS5 关键词检索与 RRF 融合排序
- OpenAI 兼容接口的流式问答和文档引用
- 会话创建、重命名、历史记录和删除
- Vue 3、Pinia、Element Plus 管理与聊天界面

## 技术栈

- Python 3.12、FastAPI、SQLAlchemy 2、Alembic、SQLite
- SentenceTransformers、Qdrant、OpenAI Python SDK
- Vue 3、TypeScript、Vite、Pinia、Element Plus
- pytest、Vitest、Playwright、Ruff、Black

## 本地启动

### 1. 配置环境

复制 `.env.example` 为 `.env`，至少替换以下配置：

```dotenv
JWT_SECRET_KEY=使用密码生成器创建的至少32字节随机字符串
QDRANT_URL=http://127.0.0.1:6333
OPENAI_API_KEY=你的API密钥
OPENAI_MODEL=gpt-4o-mini
```

`OPENAI_BASE_URL` 可以指向任何兼容 OpenAI Chat Completions 接口的服务。首次执行 Embedding 时会下载模型，因此可能需要较长时间和网络访问。

### 2. 启动 Qdrant

本机已有 Docker 时，可以单独启动 Qdrant：

```powershell
docker run --name network-rag-qdrant -p 6333:6333 -p 6334:6334 -v network-rag-qdrant:/qdrant/storage qdrant/qdrant:v1.12.5
```

### 3. 启动后端

在项目根目录执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.lock
cd backend
alembic upgrade head
uvicorn app.main:app --reload
```

`requirements.txt` 声明允许的依赖范围，`requirements.lock` 固定可复现版本。日常安装和 CI 推荐使用 `pip install -r requirements.lock`；依赖范围发生变化后，执行 `uv pip compile requirements.txt --universal --output-file requirements.lock` 更新锁文件。

后端地址为 `http://127.0.0.1:8000`，OpenAPI 文档位于 `http://127.0.0.1:8000/docs`，健康检查位于 `http://127.0.0.1:8000/health`。

依赖安装和数据库迁移完成后，也可以在项目根目录用一个命令同时启动前后端：

```powershell
python -m scripts.dev
```

按 `Ctrl+C` 会同时停止两个服务。端口被占用时，可以通过
`--backend-port` 和 `--frontend-port` 指定其他端口；执行
`python -m scripts.dev --help` 可查看全部选项。启动器会等待后端健康检查
通过后再启动前端，优先使用项目 `.venv` 中的 Python，并自动同步前端
API 地址与后端 CORS 来源配置。

### 4. 创建管理员

数据库迁移完成后，在 `backend` 目录执行：

```powershell
python -m app.cli.create_admin
```

命令会通过隐藏输入读取密码，不提供默认账号或默认密码。可以使用 `--username` 指定用户名。

### 5. 启动前端

```powershell
cd frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173`。管理员登录后应先上传文档并执行索引，普通用户随后才能检索这些内容。

## Docker Compose

完整环境包含前端、后端和 Qdrant。Compose 默认以**生产模式**启动后端，因此必须显式
提供随机 JWT 密钥与 Qdrant API Key；本地明文 HTTP 访问还需要显式声明开发环境：

```powershell
$env:JWT_SECRET_KEY = "使用密码生成器创建的至少32字节随机字符串"
$env:QDRANT_API_KEY = "另一个随机字符串"
$env:OPENAI_API_KEY = "你的API密钥"
$env:APP_ENV = "development"   # 本地明文 HTTP；HTTPS 部署请留空并设 AUTH_COOKIE_SECURE=true
docker compose up --build
```

访问 `http://127.0.0.1:8080`。SQLite 数据、上传文档和 Qdrant 数据分别保存在 Docker Volume 中。首次启动后创建管理员：

```powershell
docker compose exec backend python -m app.cli.create_admin
```

生产模式（`APP_ENV=production`，默认值）会拒绝默认或短于 32 字节的 JWT 密钥、
`AUTH_COOKIE_SECURE=false` 和 `APP_DEBUG=true`，所以放到 HTTPS 后面时只需设置
`AUTH_COOKIE_SECURE=true` 并妥善保管 `JWT_SECRET_KEY`、`QDRANT_API_KEY` 和
`OPENAI_API_KEY`。

后端容器以 uid 10001 的非 root 用户运行；Qdrant 只在 Compose 内部网络暴露，不再
发布到宿主端口，且必须携带 API Key。若沿用旧的 `app_data`/`qdrant_data` 卷，卷内
文件属主仍是 root，需要重建（`docker compose down -v`，会删除数据）或在卷内修正
属主后再启动。

## 主要环境变量

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./network_rag.db` | SQLAlchemy 数据库连接 |
| `DOCUMENT_UPLOAD_DIR` | `data/uploads` | 上传文件存储目录 |
| `DOCUMENT_MAX_UPLOAD_BYTES` | `52428800` | 单文件上限，默认 50 MB |
| `QDRANT_URL` | `http://127.0.0.1:6333` | Qdrant 服务地址 |
| `QDRANT_API_KEY` | 空（Compose 必填） | Qdrant API 密钥 |
| `QDRANT_COLLECTION_NAME` | `document_chunks` | 向量集合名称 |
| `RETRIEVAL_MIN_SCORE` | `0.87` | 向量相关度下限，低于它的候选不进入 prompt |
| `CHAT_HISTORY_TURNS` | `3` | 拼入检索查询的最近用户提问轮数 |
| `CHAT_HISTORY_MAX_TOKENS` | `512` | 回放对话历史的 token 预算 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容接口地址 |
| `OPENAI_API_KEY` | `not-required` | LLM API 密钥 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 对话模型名称 |
| `OPENAI_TEMPERATURE` | `0` | 采样温度，0 表示可复现输出 |
| `OPENAI_MAX_TOKENS` | `1024` | 单次回答长度上限 |
| `INDEXING_LEASE_SECONDS` | `900` | 索引租约，超时后文档可被重新索引 |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_WINDOW_SECONDS` | `5` / `300` | 登录限流（按客户端+用户名） |
| `CHAT_MAX_REQUESTS` / `CHAT_WINDOW_SECONDS` | `30` / `60` | 聊天接口限流（按用户） |
| `FRONTEND_ORIGIN` | `http://127.0.0.1:5173` | CORS 允许的前端来源 |
| `JWT_SECRET_KEY` | 仅开发默认值 | JWT 签名密钥，生产环境必须替换 |
| `AUTH_COOKIE_SECURE` | `false` | HTTPS 部署时必须设为 `true` |

限流是**进程内**实现（线程安全的滑动窗口），单进程部署足够；多 worker 或水平扩容
时必须换成共享存储（Redis）或在前置网关上做限流。

## 质量检查

后端：

```powershell
.venv\Scripts\ruff.exe check backend
.venv\Scripts\black.exe --check backend
.venv\Scripts\pytest.exe
```

前端：

```powershell
cd frontend
npm run type-check
npm run test
npm run build
npm run test:e2e
```

GitHub Actions 会在推送和拉取请求中执行以上检查。Playwright 当前覆盖登录与角色控制、文档管理、聊天引用及会话操作；后端测试通过 FastAPI 依赖替换隔离外部 Embedding、Qdrant 和 LLM 服务。

## 数据库迁移与索引重建

应用启动前必须先把数据库升级到最新版本：

```powershell
cd backend
alembic upgrade head
```

`backend/tests/test_database_contract.py` 会直接运行迁移并与 ORM 模型比对，用于
拦住"模型已改、迁移没跟上"的漂移；同时校验 SQLite 外键约束与级联删除是否真正
生效。

FTS5 在写入行时就完成分词，因此**改变分词方式的迁移不会自动重新分词已有内容**。
迁移后如检索结果异常，可重建关键词索引（只重新分词，不重新解析文档、不调用
Embedding 与 LLM，因此没有额外 API 成本）：

```powershell
cd backend
python -m app.cli.rebuild_search_index
```

关键词检索使用 jieba 分词以支持中文。SQLite 内置的 `unicode61` 分词器会把连续
中文当作单个词元，导致中文查询命中率为 0，因此索引期与查询期统一通过
`app/services/tokenization.py` 切词，并剔除停用词与纯标点。

## 运维要点

**切块尺寸变更后需要重新索引。** 当前默认目标是 320 cl100k token、重叠 48、硬上限
400（历史版本是 500/80）。已索引文档的切块不会自动重切，`rebuild_search_index`
也只重新分词、不重新解析，所以要让旧文档用上新尺寸，需要在管理界面对它们重新执行
索引（解析 → 切块 → Embedding → 写入两个存储）。

**大文件建议用后台索引接口。** `POST /api/admin/documents/{id}/index/async` 先
claim 任务并立即返回 `202` 与 `job_id`，解析、切块、Embedding、写两个存储都在响应
之后执行（任务自持数据库会话，与流式回答的持久化同理）；进度通过文档状态体现
（`processing` → `indexed`/`failed`），失败同样会自动补偿并落到 `failed`。原来的
同步接口 `POST /api/admin/documents/{id}/index` 保留，前端仍使用它。

**卡住的索引任务会自动回收。** 索引任务带租约（`INDEXING_LEASE_SECONDS`，默认 15
分钟）：worker 崩溃后文档不会永久停在“处理中”，重新点击索引会先释放过期租约再
claim；也可以用命令做全库清扫：

```powershell
cd backend
python -m app.cli.reap_stale_indexing
python -m app.cli.reap_stale_indexing --lease-seconds 300
```

**删除是可重试的。** 删除文档时先把状态置为 `pending_delete`，再依次清理 Qdrant、
FTS5 与源文件，最后才删行。任一步失败都会返回 503 并保留该状态，向量服务恢复后
重复删除同一文档即可完成，不会留下孤儿向量。关键词索引清理与行删除在**同一个
事务**里提交，因此不会出现「文档还在、关键词却搜不到」的中间态。

**事务边界在请求层。** 仓储只 `flush()`，一次请求就是一个事务：成功统一提交、异常
统一回滚（见 `CONTRIBUTING.md` 的「事务与仓储规则」）。请求之外的写入各自持有会话
并显式提交——后台索引任务、流式回答持久化、CLI 命令；文档删除会先单独提交
`pending_delete` 标记，再在另一个事务里完成索引清理与删行。

**列表接口都是分页的。** 文档、用户、会话列表接受 `limit`（1–200，默认 100）与
`offset`，并在响应头返回未分页的总数 `X-Total-Count`（跨域时通过 CORS
`expose_headers` 暴露）。前端目前按默认页大小取第一页，分页控件属于后续工作。

**登出会立即吊销已有 token。** `users.token_version` 随登出递增，JWT 携带 `ver`
声明，版本不匹配的 token 一律 401。新增改密接口时同样需要递增该版本。

## 目录

```text
backend/
  alembic/          数据库迁移
  app/
    api/            FastAPI 路由
    auth/           密码、JWT、Cookie 与权限依赖
    cli/            管理员创建与索引重建命令
    core/           配置、日志和异常响应
    db/             SQLAlchemy 引擎、Session 与 schema 定义
    models/         ORM 模型
    repositories/   SQLite、FTS5 与 Qdrant 数据访问
    schemas/        Pydantic 请求与响应模型
    services/       解析、分词、索引、检索、引用和聊天服务
    rag/            RAG 依赖组装
  tests/            后端单元与 API 测试
frontend/
  src/
    api/             HTTP 与 SSE 客户端
    components/      通用组件
    layouts/         页面布局
    router/          路由与角色守卫
    stores/          Pinia 状态管理
    views/           聊天和管理页面
  tests/             Vitest 测试
  e2e/               Playwright 工作流测试
```

## 参与开发

分支策略、提交信息规范、钩子安装与数据库迁移规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。
