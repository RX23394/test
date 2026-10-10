# 贡献指南

本项目采用**主干开发 + 短生命周期特性分支**。`main` 始终可发布，任何改动都
经过一个特性分支、一次本地质量门禁、一个 PR。

## 1. 一次性设置

```powershell
# 提交模板：git commit 时会自动带出规范注释
git config commit.template .gitmessage

# 行尾归一化：本仓库统一使用 LF
git config core.autocrlf false

# 安装提交钩子（需要先装好 .venv 依赖）
.venv\Scripts\pip.exe install -r requirements.lock
.venv\Scripts\pre-commit.exe install --hook-type pre-commit --hook-type pre-push
```

钩子分两道，与 CI 完全一致：

| 阶段 | 执行内容 | 目的 |
| --- | --- | --- |
| `pre-commit` | `ruff check`、`black --check`、行尾/空白/大文件/私钥检查 | 秒级反馈，拦住格式与低级问题 |
| `pre-push` | `pytest`（含 80% 覆盖率门槛） | 推送前拦住测试回归 |

不要用 `ruff format` 替代 `black`：两者对真实代码的取舍不同，钩子与 CI 用不同
格式器会让每个 PR 都变成格式争论。

## 2. 分支命名

分支名格式：`<type>/<short-topic>`，topic 用小写连字符，2–5 个词。

```text
feat/fts-chinese-tokenizer
fix/sse-session-lifecycle
refactor/repository-transaction-boundary
docs/git-workflow
chore/bump-qdrant-client
```

只允许从最新的 `main` 切出，且一个分支只做一件事：

```powershell
git switch main
git pull --ff-only
git switch -c feat/fts-chinese-tokenizer
```

## 3. 提交信息

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```text
<type>(<scope>): <祈使句摘要，不超过 72 字符>

为什么：这个改动解决的具体问题，最好带证据。
怎么做：方案要点，以及评审者否则需要猜的部分。
验证：实际执行的命令与结果。
```

`type` 取值：`feat` `fix` `refactor` `perf` `test` `docs` `build` `ci` `chore` `revert`。

`scope` 取值：`backend` `frontend` `rag` `auth` `db` `fts` `chat` `search` `docs` `ci` `deps`。

示例：

```text
fix(fts): 中文关键词检索命中率从 0 恢复

为什么：FTS5 使用 tokenize='unicode61'，连续 CJK 字符被当作单个 token。
实测「配置BGP邻居关系时，需要在对等体下指定对端自治系统号。」只会索引出
4 个多字符 token，查询「配置」「邻居」「自治系统」均返回 0 行，混合检索
静默退化为纯向量检索。

怎么做：新增 content_tokens 列存放 jieba 词流，索引期与查询期共用
TokenizationService；同时剔除停用词与纯标点，避免 AND 语义把召回压到 0。

验证：pytest（新增 23 个中文检索用例）、ruff、black 全部通过；
本地 562 条 chunk 重建后「配置」「邻居」均可命中。
```

提交粒度：**一次提交一个逻辑改动**。格式化与重命名不要混进功能提交。

## 4. 合并前质量门禁

```powershell
# 后端
.venv\Scripts\ruff.exe check backend scripts alembic
.venv\Scripts\black.exe --check backend scripts alembic
.venv\Scripts\pytest.exe

# 前端
cd frontend
npm run type-check
npm run test
npm run build
```

CI 会重复执行以上全部内容，外加 `docker compose config` 校验。**本地不通过就不要
提 PR**，否则只是把反馈延迟到流水线。

## 5. 数据库迁移规则

- **绝不修改历史迁移**。`alembic/versions` 下的既有文件是已发布的事实，改它会
  让已升级的库与全新建的库产生分歧。
- 新迁移必须自包含：不要 `from app.xxx import`。迁移描述的是**当时**的 schema，
  应用代码会继续演进（见 `20260930_0008` 内联 jieba 的写法）。
- 必须同时提供可用的 `downgrade()`。
- 涉及 SQLite 的 `ALTER` 必须用 `op.batch_alter_table`。
- 新增迁移后必须确认迁移与 ORM 模型无漂移：

  ```powershell
  .venv\Scripts\pytest.exe backend\tests\test_database_contract.py
  ```

  该测试直接跑迁移并比对 `Base.metadata`，而不是用 `create_all` 建表——后者永远
  发现不了漂移（历史上就因此漏掉了 `documents.indexing_job_id` 缺失）。
- 若迁移改变了文本分词方式，FTS5 已写入的行不会自动重新分词，需要补一步重建并
  在 PR 中说明：

  ```powershell
  cd backend
  python -m app.cli.rebuild_search_index
  ```

## 6. 事务与仓储规则

**仓储只 `flush()`，不 `commit()`。** 一次请求就是一个事务：`app/db/session.py` 的
`get_db` 在请求成功时提交、抛异常时回滚。因此：

- 新增仓储写方法时用 `self._session.flush()`（需要主键或默认值时也用 flush，不要用
  commit + refresh）；
- 需要「中途落库」的流程由调用方显式 `session.commit()`，并在注释里说明为什么必须
  单独提交（例如文档删除要先提交 `pending_delete` 标记，这样外部清理阶段崩溃后仍能
  看到意图）；
- 请求之外的写入必须自持会话并显式提交，参考 `app/services/indexing_jobs.py`、
  `routes/chat.py:persist_stream_exchange` 与 `app/cli/*`；
- 测试用 conftest 的 `session_factory`：它的会话在块正常结束时提交，等价于一次请求，
  所以不要依赖「调用仓储即落库」。

## 7. PR 流程

1. 推送分支：`git push -u origin feat/fts-chinese-tokenizer`
2. 按 `.github/PULL_REQUEST_TEMPLATE.md` 填写（涉及迁移时必须填迁移检查项）
3. 确保 CI 全绿后再合并；合并使用 squash 或 merge commit 均可，但**不要**
   把无关改动带进同一个 PR
4. 合并后删除分支：

   ```powershell
   git switch main
   git pull --ff-only
   git branch -d feat/fts-chinese-tokenizer
   ```

## 8. 当前仓库状态说明

本仓库此前**从未提交过**，`main` 的第一个提交是当前工作树的完整快照。以下本地
文件被 `.gitignore` 排除，不进入版本控制：

- `.env`（含真实密钥，仅本地保留）
- `backend/network_rag.db`、`data/uploads/*`（本地数据）
- `.venv/`、`frontend/node_modules/`、构建产物

**密钥纪律**：`.env` 不进库，也不要把真实密钥粘进任何被跟踪的文件。`.env.example`
只放占位符。提交前建议自查：

```powershell
git diff --cached --name-only | Select-String -Pattern '\.env$|\.db$|api[_-]?key'
```
