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

Windows 上也可以直接运行项目根目录的 `start-dev.bat`：它会检查 `.venv`、
`.env` 和端口占用情况，执行 `alembic upgrade head`，在缺少
`frontend\node_modules` 时自动 `npm ci`，然后各开一个窗口启动两个服务，并在
`/health` 与前端首页都返回 200 之后才报告成功。`start-dev.bat --skip-migrate`
跳过迁移检查，`start-dev.bat --no-browser` 不自动打开浏览器。配套的
`stop-dev.bat` 会按端口终止两个服务及其进程树（uvicorn 的 reloader 和
`npm run dev` 的包装进程都算在内），适合窗口已关但端口仍被占用的情况。

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
| `DATABASE_URL` | `sqlite:///./network_rag.db` | SQLAlchemy 数据库连接；相对 SQLite 路径固定解析到 `backend/`，与实际启动目录无关 |
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
| `EMBEDDING_CACHE_DIR` | `.runtime/cache` | 编码器编译缓存位置，指向项目内目录以避免依赖系统临时目录 |
| `EMBEDDING_OFFLINE` | `true` | 只读本地 Hugging Face 缓存、不联网校验；缓存不完整时需设为 `false` |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_WINDOW_SECONDS` | `5` / `300` | 登录限流（按客户端+用户名） |
| `CHAT_MAX_REQUESTS` / `CHAT_WINDOW_SECONDS` | `30` / `60` | 聊天接口限流（按用户） |
| `FRONTEND_ORIGIN` | `http://127.0.0.1:5173` | CORS 允许的前端来源；为回环地址时自动接受 `localhost`、`127.0.0.1`、`[::1]` 三种写法 |
| `JWT_SECRET_KEY` | 仅开发默认值 | JWT 签名密钥，生产环境必须替换 |
| `AUTH_COOKIE_SECURE` | `false` | HTTPS 部署时必须设为 `true` |

限流是**进程内**实现（线程安全的滑动窗口），单进程部署足够；多 worker 或水平扩容
时必须换成共享存储（Redis）或在前置网关上做限流。

### 前端报 “Failed to fetch” 时怎么查

浏览器的 `fetch` 把两类完全不同的问题都报成同一句话：请求根本没发出去（后端没启动、
端口不对），以及**响应回来了但被 CORS 拦下**。第二种最容易被误判，因为 DevTools 的
Network 面板仍然会显示真实状态码，而 JS 只拿到 `TypeError: Failed to fetch`，
后端返回的 `message` 永远读不到。

判定顺序：

1. Network 面板里看那条请求。显示 `(failed)` 且没有状态码，说明连接层失败，先确认
   后端在监听：浏览器打开 `http://127.0.0.1:8000/health`。
2. 有状态码但控制台报 CORS，说明是**来源不匹配**。本站只允许 `FRONTEND_ORIGIN`
   配置的来源（回环地址自动接受三种写法），所以用 `localhost:5173` 打开前端、而配置
   写的是 `127.0.0.1:5173` 时会被拒绝；反过来也一样。
3. 想看后端到底抛了什么，运行诊断脚本，它在进程内驱动一次真实的流式提问并打印完整
   回溯（会临时建一个用户和会话，结束后删除）：

   ```powershell
   .venv\Scripts\python.exe diagnose_chat_500.py
   ```

未捕获异常由 `ServerErrorMiddleware` 在最外层生成 500，它不经过 `CORSMiddleware`，
所以后端显式在 `app/core/exceptions.py` 里补上了 CORS 头；否则任何 500 在跨域场景下
都会被浏览器吞掉，只留下 `Failed to fetch`。

### 启动环境：别在受限/沙箱终端里启动后端

**症状**：`/health` 与所有读接口都正常，但**任何写操作都失败** —— 新建会话返回 500、
聊天结束时报 `Conversation could not be saved`，日志里是
`sqlite3.OperationalError: attempt to write a readonly database`。

**原因**：后端进程被拉起它的受限环境（编辑器、agent 工具或沙箱终端）拦截了文件写入。
此时那个数据库文件对同期从普通终端启动的进程**完全可写**（`pragma integrity_check`
返回 `ok`、`INSERT` 正常），因此**既不是文件权限问题，也不是应用缺陷** —— 换一个启动
上下文，同一份代码、同一个数据库文件就一切正常。

**处理**：在**独立的**普通终端里启动。开始菜单打开 PowerShell，不要用编辑器或 agent
工具的内置终端；从那些界面里双击 `.bat` 同样会继承受限环境。

```powershell
cd 'F:\AI CODE\lnternet'
.\start-dev.bat
```

判断是否正常：进程树里不应出现线程数达数十、占用数百 MB 内存的
`python.exe -c "from multiprocessing.spawn import spawn_main; ..."` 子进程 ——
它在受限环境下会被注入。

**在 Windows 上还有一个更隐蔽的成因：完整性级别。** 从沙箱/受限环境启动的进程运行在
**低完整性**级别，而 Windows 的 No-Write-Up 规则禁止低完整性进程写入中等完整性的
对象 —— 这与文件权限无关，`icacls` 里看起来一切正常也无济于事。判断方法：

```powershell
icacls 'F:\AI CODE\lnternet\backend' | Select-String 'Mandatory Label'
```

没有输出即为默认的中等完整性。受限进程若要写这个目录（SQLite 每次写入都必须在 `.db`
旁边**创建 `-journal` 文件**），就在**管理员** PowerShell 里给它打上与项目其它可写目录
一致的标签：

```powershell
icacls 'F:\AI CODE\lnternet\backend' '/setintegritylevel' '(OI)(CI)Low'
```

标记为 Low 不会放宽安全性：它只允许低完整性进程写入该目录，普通用户进程照常读写。
项目里的 `.runtime/` 本来就有这个标签 —— 这也正好解释了为什么模型缓存、临时目录与
诊断脚本一直正常，唯独数据库写入失败。

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

如果后端曾临时指向过另一份数据库副本（例如 `DATABASE_URL` 被环境变量覆盖成
`.runtime/network_rag.db`），副本里会多出原库没有的数据。`finish_setup.py` 用来
把这种副本合并回项目库，并确保 `.env` 里有 `RETRIEVAL_MIN_SCORE`：

```powershell
.venv\Scripts\python.exe finish_setup.py
```

它会先把两份库分别备份到 `.runtime/backup-project-<时间>.db` 与
`.runtime/backup-runtime-<时间>.db`，再按主键补齐副本里多出的 `messages` 行、
刷新有差异的 `users` 行，最后打印逐表计数校验。命令是幂等的，可以重复执行；
`--skip-env` 不修改 `.env`，`--delete-runtime-copy` 在合并后删除副本。

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

**融合结果限制同一文档最多占 2 个席位。** RRF 按**名次**计分，因此一个文档只要在
向量排名里占据相邻的若干名次，就能把 8 个提示词席位中的大部分据为己有。实测（内置
语料、提问 `OSPF 邻居关系是怎么建立的？`）：中文《STP与RSTP与MSTP_自编笔记.md》占据
S1、S4–S8 共 6 席，而真正含答案的 `RFC2328_OSPFv2.txt` 排在第 33 位——当时
`VECTOR_SEARCH_LIMIT = 30`，它**在按分数过滤之前就被 Qdrant 截断了**，从未进入候选集。

因此 `app/services/search.py` 同时做两件事，二者缺一不可：

- `VECTOR_SEARCH_LIMIT` 由 30 提高到 **200**。单提高上限**不会**改变结果（实测在
  30/100/200/300 四个取值下 Top8 完全相同），因为融合顺序由名次决定、与池子大小无关；
  它只是让排在第 33 位的正确文档有机会进入候选集。
- `MAX_CHUNKS_PER_DOCUMENT = 2` 限制单一文档在提示词中的席位。仅加上限同样不够——
  排第 33 位的文档在 limit=30 时依然进不来。

两者合起来才把正确文档送进提示词：上述提问下 `RFC2328_OSPFv2.txt` 现在占 S7–S8
（`scripts/probe_retrieval_rank.py` 显示它从 `OUTSIDE LIMIT` 变为 `in candidates`），
`BGP 路由反射器的作用是什么？` 则在 Top8 中出现 `RFC4456_BGP路由反射.md` 与
`RFC4271_BGP-4.md`，Top8 覆盖的文档数从 2 提升到 5。

注意这**只修正席位分配，不改变排序质量**：排序仍由 embedding 模型决定，而
`multilingual-e5-small` 会把不相关的中文笔记排在正确的英文 RFC 之前（差距约
0.02——实测 0.8554 对 0.8332）。要真正提高排序质量需要更换模型（见 `docs/knowledge-base.md`）。

排查检索问题时，这两个脚本不需要启动服务即可运行（均在项目根目录执行）：

```powershell
# 每个文档在向量排名中的首次出现位置，标注是被上限截掉还是被阈值滤掉
.venv\Scripts\python.exe scripts\probe_retrieval_rank.py "你的问题"

# 完整走一次真实提问，打印流式答案与引用来源
.venv\Scripts\python.exe scripts\ask.py "你的问题"
```

**可用临时目录由应用自己保证。** 若系统临时目录不可写（受限/沙箱环境常见：你自己的
shell 能写 `%TEMP%`，但被 harness 拉起的服务进程不能），Python 的 `tempfile` 会逐个
探测候选目录并最终抛 `FileNotFoundError: No usable temporary directory found`。而
`torch._dynamo` 与 `huggingface_hub` 都在**导入期**解析临时路径，于是加载编码器时整个
请求失败——表现为首个提问返回 503，日志里是那串候选目录列表。

`app/core/tempdir.py` 的 `ensure_usable_temp_directory()` 在应用启动时
（`create_app()`）以及导入编码器之前各执行一次：它能写系统临时目录就原样保留；不能写
就改用 `.runtime/tmp`，并同时设置 `tempfile.tempdir` 与 `TEMP`/`TMP`。

必须直接赋值 `tempfile.tempdir` 而不是只设环境变量：`tempfile` 会记住先前探测失败的
结果，显式赋值才能跳过它的搜索。实测在"所有候选都不可写"的条件下，此前会抛
`FileNotFoundError` 的 `torch._inductor` 缓存路径能正常解析，且完整提问返回 200。

若机器无法直连 Hugging Face，先单独把模型取到本地缓存再启动后端（这一步失败时会把
真实原因直接打出来，不必等到提问才在 500 里猜）：

```powershell
cd backend
..\.venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small'); print('model cached')"
```

模型取不到时，聊天接口会返回 **503** 与 `Embedding model is unavailable`（而不是裸
500），服务端日志中保留完整根因。使用镜像站时通过 Hugging Face 自身的
`HF_ENDPOINT` 环境变量指定，例如 `HF_ENDPOINT=https://hf-mirror.com`。

**模型已缓存后应用会自动进入离线模式。** 模型落在 Hugging Face 缓存里（默认
`%USERPROFILE%\.cache\huggingface\hub\models--intfloat--multilingual-e5-small`，约
493 MB）。只要缓存存在，`EMBEDDING_OFFLINE=true`（默认值）就让进程完全不去查
`huggingface.co`：`huggingface_hub` 的 `HF_HUB_OFFLINE` 是在其 **import 时**读入
模块级常量的（`huggingface_hub/constants.py`），因此**事后在 shell 里 export 是无效的**
——只要 `huggingface_hub` 已被任何模块导入过就来不及了。所以应用在导入编码器之前
（`ensure_embedding_caches()`）自己设置这两个变量，不需要你配任何东西。

联网被墙时若不设这一项，每个文件都会 HEAD 请求并重试 5 次，日志刷满
`WinError 10054`，**每次首次提问要白等约 1 分钟**。实测开启后纯本地加载约 18 秒、
零重试日志。缓存不完整时会被明确报错（503 `Embedding model is unavailable`），
而不是静默降级；此时把 `EMBEDDING_OFFLINE=false` 并保证能访问 Hub（或设
`HF_ENDPOINT=https://hf-mirror.com`）即可补齐缓存。

索引本身是 FTS5 的 **external-content 表**：切块正文与元数据存放在普通表
`document_chunk_rows`（`document_id` 上有索引），虚拟表只保存词元流，两者由触发器
保持同步。因此按文档清理切块走索引查找，不再是虚拟表全表扫描；删除文档时外键级联
也会经由触发器同步删除索引项。

## 运维要点

**切块尺寸用 Embedding 自己的分词器计量。** 当前默认目标是 320 embedding token、
重叠 48、硬上限 450（历史版本是 500/80，后来是 320 cl100k token / 上限 400）。
`intfloat/multilingual-e5-small` 的分词器对 ASCII 密集内容（RFC 里的 `+-+-+-+-+`
rule 图、表格、参考文献列表）会数出远超 cl100k 的 token 数：实测有切块 cl100k 只有
290，编码器却需要 901 个，于是索引直接以 `EmbeddingInputTooLongError` 失败——因为
编码器在 512 token 处截断，超过的尾巴会被静默丢弃。`app/services/token_counter.py`
的 `embedding` 后端负责按真实编码器计量，`EMBEDDING_PASSAGE_OVERHEAD` 与
`passage: ` 前缀各计一次（不是逐词计），已索引文档的切块不会自动重切，
`rebuild_search_index` 也只重新分词、不重新解析，所以要让旧文档用上新尺寸，需要在
管理界面对它们重新执行索引（解析 → 切块 → Embedding → 写入两个存储）。

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
