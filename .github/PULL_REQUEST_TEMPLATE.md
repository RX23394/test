# 变更说明

## 这个 PR 做了什么

<!-- 一句话说明目的。关联 Issue：Closes #123 -->

## 变更类型

- [ ] feat 新功能
- [ ] fix 缺陷修复
- [ ] refactor 重构（不改变外部行为）
- [ ] perf 性能优化
- [ ] test 测试补充
- [ ] docs 文档
- [ ] build / ci 构建与流水线
- [ ] chore 杂项
- [ ] revert 回滚

## 影响范围

- [ ] backend（FastAPI / SQLAlchemy / Alembic）
- [ ] frontend（Vue 3 / Pinia / TypeScript）
- [ ] RAG 管线（解析 / 切块 / 检索 / 提示词）
- [ ] 数据库迁移（**必须说明升级与回滚方式**）
- [ ] 依赖变更（`requirements.txt` / `requirements.lock` / `package.json`）
- [ ] 配置或环境变量（需同步更新 `.env.example`）

## 数据库迁移检查（涉及迁移时必填）

- [ ] 新增迁移文件，**未修改任何历史迁移**
- [ ] `alembic upgrade head` 在空库上成功
- [ ] `alembic upgrade head` 在已有数据上成功
- [ ] `alembic downgrade -1` 可回滚
- [ ] 迁移与 ORM 模型无漂移（`test_migrations.py` 通过）
- [ ] 说明是否需要重建索引或回填数据

## 验证方式

<!-- 粘贴实际执行的命令与结果，不要只写"已测试" -->

```
.venv\Scripts\ruff.exe check backend
.venv\Scripts\black.exe --check backend
.venv\Scripts\pytest.exe
cd frontend && npm run type-check && npm run test && npm run build
```

## 自查清单

- [ ] 遵循 AGENTS.md：本次只实现一个 Feature
- [ ] 未修改无关代码、未删除已有接口
- [ ] 新增/修改行为都有对应测试
- [ ] 测试在**未修改**代码时会失败（证明测试有效）
- [ ] 如有必要已更新 README / `.env.example`
- [ ] 提交信息符合 Conventional Commits
- [ ] 无密钥、令牌、真实 API Key 进入暂存区

## 风险与回滚

<!-- 这个变更最坏会导致什么？出问题怎么退回去？ -->
