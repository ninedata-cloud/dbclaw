# Execute Query Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 SQL 类数据库 connector 的 `execute_query()` 返回结构，修复 `execute_any_sql` 在 DML/DDL 场景下的兼容性问题，并保证错误信息不再出现空字符串，同时验证查询页消费方不受破坏。

**Architecture:** 保持现有 `execute_any_sql -> SkillContext.execute_query -> backend.utils.db_connector.execute_query -> connector.execute_query` 链路不变，只在 SQL connector 层和统一异常包装层修复行为。所有 SQL connector 统一返回同一数据契约；上层 `db_connector` 统一补 `success`、`data`，并新增 query router 视角的回归测试，确保现有查询页面只读链路保持兼容。

**Tech Stack:** Python async/await、FastAPI 后端、各数据库驱动（aiomysql、asyncpg、oracledb/cx_Oracle、pymssql、达梦驱动等）、现有脚本式测试

---

## Scope and boundaries

### In scope
- `backend/utils/db_connector.py` 的统一异常兜底与包装行为
- 所有 **SQL 类 connector** 的 `execute_query()` 返回契约统一：
  - MySQL
  - PostgreSQL
  - openGauss
  - Oracle
  - SQL Server
  - DM
  - TiDB
  - OceanBase
- `backend/routers/query.py` 的消费方回归测试，确保查询页依赖的字段不被破坏

### Out of scope
- `backend/skills/builtin/execute_any_sql.yaml`：不修改，问题不在 skill 本身
- MongoDB / Redis：当前缺陷根因是 SQL DML/DDL 无结果集处理，它们不是本次修复目标；除非实现中发现 query router 或 skill 路径真实依赖它们出现同类问题，否则不纳入本次改动
- 大规模重构 connector 架构、抽象公共基类、重写 SQL 解析器

---

## File Map

### Core execution path
- Modify: `backend/utils/db_connector.py`
  - 统一异常兜底，确保 `error` 非空，补充 `error_type`
  - 保持对上层 skill 的兼容返回（`success` / `data`）

### SQL connectors to normalize
- Modify: `backend/services/mysql_service.py`
- Modify: `backend/services/postgres_service.py`
- Modify: `backend/services/opengauss_service.py`
- Modify: `backend/services/oracle_service.py`
- Modify: `backend/services/sqlserver_service.py`
- Modify: `backend/services/dm_service.py`
- Modify: `backend/services/tidb_service.py`
- Modify: `backend/services/oceanbase_service.py`

### Consumer regression coverage
- Verify behavior of: `backend/routers/query.py`
  - 通过测试覆盖其对 `columns/rows/row_count/execution_time_ms/truncated/message` 的消费

### Tests
- Create: `test_execute_query_unification.py`
  - 针对统一契约写失败测试
  - 使用 mock/stub 隔离真实数据库依赖
  - 先覆盖上层包装与消费方，再覆盖各 connector 分支

---

## Unified Return Contract

所有 **SQL connector** 的 `execute_query()` 必须返回：

```python
{
    "columns": list,
    "rows": list,
    "row_count": int,
    "execution_time_ms": float,
    "truncated": bool,
    "message": str | None,
}
```

补充约束：
- 有结果集语句：
  - `columns` 为列名列表
  - `rows` 为二维数组
  - `row_count` 为返回行数
  - `truncated` 按现有逻辑计算
  - `message` 为 `None` 或缺省，但推荐显式 `None`
- 无结果集语句（INSERT/UPDATE/DELETE/DDL）：
  - `columns = []`
  - `rows = []`
  - `truncated = False`
  - `row_count` 为影响行数；未知时允许 `-1`
  - `message` 为 command tag / `Query OK, X rows affected` / `Statement executed successfully`

上层 `backend/utils/db_connector.execute_query()` 统一补：

```python
{
    "success": True,
    "data": result["rows"],
    ...connector_result
}
```

异常统一为：

```python
{
    "success": False,
    "error": <non-empty string>,
    "error_type": <exception class name>
}
```

---

## SQL classification boundary for PostgreSQL / openGauss

本次只做**最小可维护**分类，不实现完整 SQL 解析器。

### 规则
1. 先去掉前导空白与尾部分号
2. 去掉前导单行注释/块注释（只处理最常见前缀注释，避免明显误判）
3. 取首个关键字进行判断
4. 以下首关键字视为“结果集语句”，走 `fetch()`：
   - `SELECT`
   - `SHOW`
   - `EXPLAIN`
   - `VALUES`
   - `TABLE`
   - `DESC`
   - `DESCRIBE`
5. `WITH` 单独处理：
   - 若去注释/空白后的 SQL 以 `WITH` 开头，且后续包含 `INSERT` / `UPDATE` / `DELETE` / `MERGE` 且 **不包含** `RETURNING`，按“无结果集语句”处理
   - 其他 `WITH` 默认按结果集语句处理
6. 明确边界：
   - **不支持多语句解析**；多语句保持驱动现状
   - `RETURNING` 视为结果集语义
   - `EXPLAIN ANALYZE` 仍按结果集处理

这样能覆盖本次缺陷，又避免过度设计。

---

### Task 1: Write failing tests for top-level wrapper and consumer compatibility

**Files:**
- Create: `test_execute_query_unification.py`
- Verify: `backend/utils/db_connector.py`
- Verify: `backend/routers/query.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_db_connector_returns_non_empty_error_for_blank_exception_message():
    class BlankMessageError(Exception):
        def __str__(self):
            return ""

    class FakeConnector:
        async def execute_query(self, query):
            raise BlankMessageError()

    # monkeypatch backend.utils.db_connector.PostgreSQLConnector -> FakeConnector
    # call backend.utils.db_connector.execute_query(datasource, "UPDATE t SET x=1", allow_write=True)
    # assert success is False
    # assert error is non-empty
    # assert error_type == "BlankMessageError"

async def test_wrapper_adds_success_and_data_for_result_sets():
    # monkeypatch concrete connector class used by datasource.db_type
    # connector returns unified result-set contract without success/data
    # wrapper should add success=True and data=rows

async def test_query_router_consumes_unified_contract_without_breaking_message_and_truncated():
    # monkeypatch _get_connector_for() to return a fake connector
    # fake connector.execute_query returns unified contract
    # call router.execute_query(...)
    # assert QueryResult fields map correctly
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python test_execute_query_unification.py`
Expected: FAIL because current wrapper returns blank `error` and consumer-level behavior has not been regression-tested

- [ ] **Step 3: Write minimal implementation**

在 `backend/utils/db_connector.py` 提取统一错误消息：

```python
def _get_error_message(e: Exception) -> str:
    return str(e) or repr(e) or e.__class__.__name__
```

并返回：

```python
{"success": False, "error": error_message, "error_type": e.__class__.__name__}
```

同时确认 wrapper 始终补 `success=True` 和 `data=rows`。

- [ ] **Step 4: Run test to verify it passes**

Run: `python test_execute_query_unification.py`
Expected: PASS for wrapper / consumer compatibility cases

- [ ] **Step 5: Commit**

```bash
git add test_execute_query_unification.py backend/utils/db_connector.py
git commit -m "fix: return meaningful execute_query errors"
```

### Task 2: Write failing tests for PostgreSQL query vs execute split

**Files:**
- Modify: `test_execute_query_unification.py`
- Modify: `backend/services/postgres_service.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_postgres_select_returns_result_set_contract():
    # patch PostgreSQLConnector._connect to return fake conn
    # fake conn.fetch returns row objects with keys()/values()
    # assert columns/rows/row_count/truncated/message shape

async def test_postgres_update_returns_no_result_set_contract():
    # patch _connect to return fake conn
    # fake conn.execute returns "UPDATE 3"
    # assert columns == []
    # assert rows == []
    # assert row_count == 3
    # assert truncated is False
    # assert message == "UPDATE 3"

async def test_postgres_insert_returning_still_uses_fetch():
    # SQL: INSERT ... RETURNING id
    # assert fetch path is used and rows are returned

async def test_postgres_with_update_without_returning_uses_execute():
    # SQL: WITH x AS (...) UPDATE ...
    # assert execute path is used
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python test_execute_query_unification.py`
Expected: FAIL because current PostgreSQL implementation always calls `fetch()`

- [ ] **Step 3: Write minimal implementation**

在 `backend/services/postgres_service.py`：
- 增加轻量 SQL 分类辅助函数
- 结果集语句走 `conn.fetch(sql)`
- 无结果集语句走 `conn.execute(sql)`
- 从 command tag 解析 `row_count` 和 `message`
- 无结果集统一返回空 `columns/rows` 和 `truncated=False`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python test_execute_query_unification.py`
Expected: PASS for PostgreSQL tests

- [ ] **Step 5: Commit**

```bash
git add test_execute_query_unification.py backend/services/postgres_service.py
git commit -m "fix: normalize postgres execute_query responses"
```

### Task 3: Write failing tests for openGauss query vs execute split

**Files:**
- Modify: `test_execute_query_unification.py`
- Modify: `backend/services/opengauss_service.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_opengauss_select_returns_result_set_contract():
    ...

async def test_opengauss_ddl_returns_no_result_set_contract():
    # fake conn.execute returns "CREATE TABLE"
    # assert unified no-result-set response

async def test_opengauss_with_delete_without_returning_uses_execute():
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python test_execute_query_unification.py`
Expected: FAIL because current openGauss implementation always calls `fetch()`

- [ ] **Step 3: Write minimal implementation**

按 PostgreSQL 同样方式修改 `backend/services/opengauss_service.py`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python test_execute_query_unification.py`
Expected: PASS for openGauss tests

- [ ] **Step 5: Commit**

```bash
git add test_execute_query_unification.py backend/services/opengauss_service.py
git commit -m "fix: normalize opengauss execute_query responses"
```

### Task 4: Write failing tests for Oracle no-result-set handling

**Files:**
- Modify: `test_execute_query_unification.py`
- Modify: `backend/services/oracle_service.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_oracle_select_returns_result_set_contract():
    # fake cursor.description + fetchmany

async def test_oracle_update_does_not_fetch_without_description():
    # fake cursor.description = None
    # fake cursor.fetchmany raises if called
    # assert fetchmany is not called
    # assert no-result-set contract is returned
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python test_execute_query_unification.py`
Expected: FAIL because current Oracle implementation fetches before checking `cursor.description`

- [ ] **Step 3: Write minimal implementation**

在 `backend/services/oracle_service.py`：
- `await cursor.execute(sql)` 后先检查 `cursor.description`
- 有结果集再 `fetchmany(max_rows)`
- 无结果集直接返回统一结构
- 保持事务语义不变，不额外引入自动 commit 行为

- [ ] **Step 4: Run tests to verify they pass**

Run: `python test_execute_query_unification.py`
Expected: PASS for Oracle tests

- [ ] **Step 5: Commit**

```bash
git add test_execute_query_unification.py backend/services/oracle_service.py
git commit -m "fix: handle oracle statements without result sets"
```

### Task 5: Normalize connectors already close to the target contract

**Files:**
- Modify: `backend/services/mysql_service.py`
- Modify: `backend/services/tidb_service.py`
- Modify: `backend/services/oceanbase_service.py`
- Modify: `backend/services/sqlserver_service.py`
- Modify: `backend/services/dm_service.py`
- Modify: `test_execute_query_unification.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_mysql_no_result_set_includes_truncated_false_and_message():
    # patch _connect -> fake conn/cursor
    # assert explicit truncated=False on no-result-set path

async def test_tidb_no_result_set_includes_truncated_false_and_message():
    ...

async def test_oceanbase_no_result_set_includes_truncated_false_and_message():
    ...

async def test_sqlserver_no_result_set_matches_unified_contract():
    ...

async def test_dm_no_result_set_matches_unified_contract():
    ...
```

这些测试只覆盖**已知差异**：
- MySQL/TiDB/OceanBase 无结果集路径缺 `truncated`
- SQLServer/DM 需要验证字段完全一致

- [ ] **Step 2: Run tests to verify they fail**

Run: `python test_execute_query_unification.py`
Expected: FAIL because some connectors missing explicit `truncated=False` or other unified fields

- [ ] **Step 3: Write minimal implementation**

逐个补齐统一字段，避免顺手重构：
- 保留现有查询逻辑
- 只修正字段缺失/不一致
- 统一无结果集场景的 `truncated=False`
- 统一 `message` 风格

- [ ] **Step 4: Run tests to verify they pass**

Run: `python test_execute_query_unification.py`
Expected: PASS for MySQL/TiDB/OceanBase/SQLServer/DM normalization tests

- [ ] **Step 5: Commit**

```bash
git add test_execute_query_unification.py backend/services/mysql_service.py backend/services/tidb_service.py backend/services/oceanbase_service.py backend/services/sqlserver_service.py backend/services/dm_service.py
git commit -m "fix: normalize sql connector execute_query contracts"
```

### Task 6: Final regression verification

**Files:**
- Test: `test_execute_query_unification.py`
- Test: `test_skills.py`

- [ ] **Step 1: Run focused unification tests**

Run: `python test_execute_query_unification.py`
Expected: all tests PASS

- [ ] **Step 2: Run broader skill regression tests**

Run: `python test_skills.py`
Expected: PASS with no new failures introduced by wrapper changes

- [ ] **Step 3: Manually inspect changed SQL connectors for contract consistency**

Checklist:
- every SQL connector returns `columns`
- every SQL connector returns `rows`
- every SQL connector returns `row_count`
- every SQL connector returns `execution_time_ms`
- every SQL connector returns `truncated`
- every SQL connector returns `message` for no-result-set path

- [ ] **Step 4: Confirm query router compatibility from tests**

Expected evidence:
- router-level regression test passes
- `QueryResult` still receives valid `columns/rows/row_count/execution_time_ms/truncated/message`

- [ ] **Step 5: Commit final verification state**

```bash
git add test_execute_query_unification.py backend/utils/db_connector.py backend/services/mysql_service.py backend/services/postgres_service.py backend/services/opengauss_service.py backend/services/oracle_service.py backend/services/sqlserver_service.py backend/services/dm_service.py backend/services/tidb_service.py backend/services/oceanbase_service.py
git commit -m "fix: unify execute_query responses across sql connectors"
```

---

## Implementation Notes

- 不要修改 `backend/skills/builtin/execute_any_sql.yaml`，问题不在 skill 本身。
- 不要引入新的抽象基类或大规模重构；本次目标是统一契约，不是重写 connector 架构。
- PostgreSQL / openGauss 的 SQL 分类只做最小关键词判断，避免过度解析 SQL。
- 解析 command tag 时优先兼容：
  - `INSERT 0 1`
  - `UPDATE 3`
  - `DELETE 5`
  - `CREATE TABLE`
  - 无法解析影响行数时设为 `-1`
- 若某驱动本身不提供可靠 rowcount，不要发明数据，使用 `-1` + 明确 message。
- 测试优先用 stub/mock，不连真实数据库。
- `backend/utils/db_connector.py` 当前不是通过统一工厂获取 connector，而是直接实例化具体类；测试应 patch 具体 connector 类或其 `_connect()`，不要写成不存在的 factory patch。

## Suggested test file structure

`test_execute_query_unification.py` 建议分段：
- helper stubs / fake cursor / fake connection / fake asyncpg row
- wrapper error fallback tests
- query router consumer regression tests
- PostgreSQL tests
- openGauss tests
- Oracle tests
- MySQL-family + sync SQL tests

## Review checklist for the implementer

- 是否所有 SQL connector 都满足统一字段？
- 是否无结果集语句不再因为 `fetch` / `description` 问题报错？
- 是否任何异常都不会再产生 `error: ""`？
- 是否 `execute_any_sql` 无需改动即可受益？
- 是否 query router 的只读消费链路未被破坏？
- 是否仅做本次请求需要的最小修复，没有顺手扩展到 Mongo/Redis 或重构架构？
