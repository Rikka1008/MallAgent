# Agent 脚本与测试目录重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Alembic 迁移归入 `scripts/migrations/`，将两个冒烟脚本归入 `tests/smoke/`，同时保持现有运行命令有效。

**Architecture:** 仅移动源码并修改路径配置；Alembic revision 内容和链路不变。通过目录布局测试锁定新分类，通过 Alembic 离线编译和全量测试验证入口没有失效。

**Tech Stack:** Python 3.13、Pytest、Alembic、PowerShell、Ruff

## Global Constraints

- 不修改迁移 revision、down_revision 或数据库结构。
- `python -m alembic upgrade head` 命令保持不变。
- 两个冒烟脚本都迁移到 `tests/smoke/`，并继续支持直接执行。
- 不触碰无关未跟踪文件。

---

### Task 1: 用测试锁定目标目录

**Files:**
- Modify: `after_sales_agent/tests/unit/test_migrations.py`
- Modify: `after_sales_agent/tests/unit/test_service_smoke.py`

**Interfaces:**
- Consumes: 项目根目录 `Path(__file__).resolve().parents[2]`
- Produces: 新目录存在、旧目录和旧冒烟入口不存在的回归断言

- [ ] **Step 1: 将迁移测试路径改为新位置并增加目录断言**

```python
migrations = project_root / "scripts/migrations"
assert migrations.is_dir()
assert not (project_root / "migrations").exists()
revision = migrations / "versions/20260712_01_create_agent_memories.py"
```

- [ ] **Step 2: 增加冒烟脚本分类断言**

```python
smoke_dir = project_root / "tests/smoke"
assert (smoke_dir / "smoke_test_services.py").is_file()
assert (smoke_dir / "smoke_test_idempotency.py").is_file()
assert not (project_root / "scripts/smoke_test_services.py").exists()
assert not (project_root / "scripts/smoke_test_idempotency.py").exists()
```

- [ ] **Step 3: 运行测试确认因目录尚未移动而失败**

Run: `python -m pytest tests/unit/test_migrations.py tests/unit/test_service_smoke.py -q`

Expected: FAIL，失败原因是 `scripts/migrations` 或 `tests/smoke` 尚不存在。

---

### Task 2: 移动迁移和冒烟脚本并更新入口

**Files:**
- Move: `after_sales_agent/migrations/` → `after_sales_agent/scripts/migrations/`
- Move: `after_sales_agent/scripts/smoke_test_services.py` → `after_sales_agent/tests/smoke/smoke_test_services.py`
- Move: `after_sales_agent/scripts/smoke_test_idempotency.py` → `after_sales_agent/tests/smoke/smoke_test_idempotency.py`
- Modify: `after_sales_agent/alembic.ini`
- Modify: `README.md`

**Interfaces:**
- Consumes: Alembic `script_location` 和现有脚本直接执行入口
- Produces: `script_location = scripts/migrations`；新 README 命令 `python tests\smoke\smoke_test_services.py`

- [ ] **Step 1: 用文件移动保留完整历史内容**

移动 `env.py`、`script.py.mako`、三个 revision 和两个 smoke 文件，不编辑 revision 正文。

- [ ] **Step 2: 更新 Alembic 配置**

```ini
[alembic]
script_location = scripts/migrations
```

- [ ] **Step 3: 更新 README 的目录说明、命令与链接**

```powershell
python tests\smoke\smoke_test_services.py
```

- [ ] **Step 4: 运行目标测试确认通过**

Run: `python -m pytest tests/unit/test_migrations.py tests/unit/test_service_smoke.py -q`

Expected: PASS。

---

### Task 3: 完整验证并提交

**Files:**
- Verify: `after_sales_agent/scripts/migrations/`
- Verify: `after_sales_agent/tests/smoke/`
- Verify: `README.md`

**Interfaces:**
- Consumes: 新目录结构
- Produces: 可运行迁移入口、可直接执行冒烟脚本、干净提交

- [ ] **Step 1: 编译 Alembic 离线 SQL**

Run: `$env:DATABASE_URL='postgresql+asyncpg://unit:unit@localhost:5432/unit'; python -m alembic upgrade head --sql`

Expected: 依次生成三个 revision，最后为 `20260715_03`。

- [ ] **Step 2: 运行全量质量检查**

Run: `python -m pytest -q`

Expected: 全部通过。

Run: `python -m ruff check app tests scripts`

Expected: `All checks passed!`

Run: `python -m compileall -q app tests scripts`

Expected: exit code 0。

- [ ] **Step 3: 检查路径引用和补丁格式**

Run: `rg -n "migrations/|migrations\\|smoke_test_services|smoke_test_idempotency" README.md alembic.ini tests scripts`

Expected: 只出现新路径或迁移业务名称，不出现旧文件入口。

Run: `git diff --check`

Expected: 无错误。

- [ ] **Step 4: 提交**

```powershell
git add README.md after_sales_agent/alembic.ini after_sales_agent/scripts after_sales_agent/tests docs/superpowers/plans/2026-07-16-agent-script-test-layout.md
git commit -m "refactor: organize agent scripts and smoke tests"
```
