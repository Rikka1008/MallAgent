# Agent 脚本与测试目录重构设计

## 目标

按文件用途重新整理 `after_sales_agent`：数据库迁移属于可执行运维脚本，统一放入 `scripts/`；冒烟检查属于测试，统一放入 `tests/`。重构只改变源码位置和引用，不改变迁移 revision、数据库结构或测试行为。

## 目标目录

```text
after_sales_agent/
├─ scripts/
│  ├─ ingest_rag_sources.py
│  └─ migrations/
│     ├─ env.py
│     ├─ script.py.mako
│     └─ versions/
│        ├─ 20260712_01_create_agent_memories.py
│        ├─ 20260713_02_create_after_sales_cases.py
│        └─ 20260715_03_create_agent_conversations.py
└─ tests/
   ├─ smoke/
   │  ├─ smoke_test_idempotency.py
   │  └─ smoke_test_services.py
   └─ unit/
```

## 兼容性

- `alembic.ini` 的 `script_location` 改为 `scripts/migrations`，因此 `python -m alembic upgrade head` 等命令保持不变。
- 迁移文件内容和 revision 链保持不变，已执行迁移的数据库无需重新迁移。
- README 中的目录说明、冒烟测试命令和链接改为新路径。
- 迁移归属测试改为读取 `scripts/migrations/versions/`。
- `tests/smoke/` 下脚本继续支持从项目根直接执行。

## 验证

- 先让目录布局测试因旧路径失败，再执行文件移动和引用更新。
- 运行迁移测试、冒烟相关单元测试和全量 Pytest。
- 运行 Alembic 离线编译、Ruff、Python 语法编译和 `git diff --check`。

