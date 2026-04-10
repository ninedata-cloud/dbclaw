# 知识库模块重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除 ChromaDB/向量技术，重建知识库模块为 AI 主动按需读取完整 Markdown 文档的系统，内置 80 篇专业数据库诊断文档。

**Architecture:** 新建 `doc_categories`（两级分类）和 `doc_documents`（含完整 Markdown content）两张表，删除旧的三张表及所有向量相关代码。AI 通过 `list_documents` 和 `read_document` 两个工具按需获取文档，不再使用语义搜索。

**Tech Stack:** FastAPI + SQLAlchemy async + PostgreSQL + Monaco Editor（本地 /lib/monaco-editor/）+ markdown-it（本地 /lib/markdown-it/）

---

## 文件结构

**删除：**
- `backend/models/knowledge_base.py`
- `backend/schemas/knowledge_base.py`
- `backend/routers/knowledge_bases.py`
- `backend/services/vector_store.py`
- `backend/services/document_chunker.py`
- `backend/services/document_parser.py`
- `backend/utils/embeddings.py`
- `frontend/js/pages/knowledge-bases.js`

**新建：**
- `backend/models/document.py`
- `backend/schemas/document.py`
- `backend/services/document_service.py`
- `backend/services/builtin_docs/__init__.py`
- `backend/services/builtin_docs/seeder.py`
- `backend/services/builtin_docs/mysql_docs.py`
- `backend/services/builtin_docs/postgresql_docs.py`
- `backend/services/builtin_docs/oracle_docs.py`
- `backend/services/builtin_docs/sqlserver_docs.py`
- `backend/routers/documents.py`
- `backend/migrations/replace_knowledge_base_with_documents.py`
- `frontend/js/pages/documents.js`

**修改：**
- `backend/database.py`
- `backend/app.py`
- `backend/config.py`
- `backend/agent/context_builder.py`
- `frontend/js/api.js`
- `frontend/index.html`
- `requirements.txt`

---

## Task 1: 新建数据库模型

**Files:**
- Create: `backend/models/document.py`

- [ ] **Step 1: 创建 DocCategory 和 DocDocument 模型**

```python
# backend/models/document.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from backend.database import Base


class DocCategory(Base):
    __tablename__ = "doc_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    db_type = Column(String(50), nullable=False)  # mysql/postgresql/oracle/sqlserver/general
    parent_id = Column(Integer, ForeignKey("doc_categories.id"), nullable=True)
    sort_order = Column(Integer, default=0)
    icon = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class DocDocument(Base):
    __tablename__ = "doc_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("doc_categories.id"), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)   # 完整 Markdown，最大约 50K 字符
    summary = Column(Text, nullable=True)    # 100 字内摘要，供 AI 目录使用
    is_builtin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, nullable=True)  # user id，内置文档为 NULL
```

- [ ] **Step 2: 提交**

```bash
git add backend/models/document.py
git commit -m "feat: add DocCategory and DocDocument models"
```

---

## Task 2: Pydantic Schemas

**Files:**
- Create: `backend/schemas/document.py`

- [ ] **Step 1: 创建 schemas**

```python
# backend/schemas/document.py
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class DocCategoryResponse(BaseModel):
    id: int
    name: str
    db_type: str
    parent_id: Optional[int] = None
    sort_order: int
    icon: Optional[str] = None
    created_at: datetime
    children: List["DocCategoryResponse"] = []
    document_count: int = 0

    class Config:
        from_attributes = True

DocCategoryResponse.model_rebuild()


class DocCategoryCreate(BaseModel):
    name: str
    db_type: str
    parent_id: Optional[int] = None
    sort_order: int = 0
    icon: Optional[str] = None


class DocDocumentCreate(BaseModel):
    title: str
    content: str
    summary: Optional[str] = None
    category_id: int
    sort_order: int = 0


class DocDocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    category_id: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class DocDocumentListItem(BaseModel):
    """目录列表项，不含完整 content"""
    id: int
    title: str
    summary: Optional[str]
    category_id: int
    is_builtin: bool
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocDocumentResponse(DocDocumentListItem):
    """完整文档，含 content"""
    content: str

    class Config:
        from_attributes = True
```

- [ ] **Step 2: 提交**

```bash
git add backend/schemas/document.py
git commit -m "feat: add document schemas"
```

---

## Task 3: 文档 CRUD Service

**Files:**
- Create: `backend/services/document_service.py`

- [ ] **Step 1: 实现 document_service**

```python
# backend/services/document_service.py
import re
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from backend.models.document import DocCategory, DocDocument
from backend.schemas.document import DocDocumentCreate, DocDocumentUpdate


def auto_summary(content: str) -> str:
    """从 Markdown 内容自动提取摘要（取前 150 字可读文本）"""
    text = re.sub(r'```[\s\S]*?```', '', content)
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^[-*+>|\s]+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n+', ' ', text).strip()
    return (text[:150].rstrip() + '...') if len(text) > 150 else text


async def get_category_tree(db: AsyncSession, db_type: Optional[str] = None):
    q = select(DocCategory).where(DocCategory.parent_id == None).order_by(DocCategory.sort_order)
    if db_type:
        q = q.where(DocCategory.db_type == db_type)
    result = await db.execute(q)
    roots = list(result.scalars().all())
    for cat in roots:
        ch = await db.execute(
            select(DocCategory).where(DocCategory.parent_id == cat.id).order_by(DocCategory.sort_order)
        )
        cat._children = list(ch.scalars().all())
    return roots


async def list_documents_by_category(db: AsyncSession, category_id: int):
    result = await db.execute(
        select(DocDocument)
        .where(DocDocument.category_id == category_id, DocDocument.is_active == True)
        .order_by(DocDocument.sort_order)
    )
    return result.scalars().all()


async def list_documents_for_ai(db: AsyncSession, db_type: Optional[str] = None) -> List[dict]:
    """返回文档目录（不含完整 content），供 AI list_documents 工具使用"""
    q = (
        select(DocDocument, DocCategory.name.label("cat_name"), DocCategory.db_type.label("cat_db_type"))
        .join(DocCategory, DocDocument.category_id == DocCategory.id)
        .where(DocDocument.is_active == True)
    )
    if db_type:
        q = q.where(DocCategory.db_type == db_type)
    q = q.order_by(DocCategory.sort_order, DocDocument.sort_order)
    result = await db.execute(q)
    return [
        {
            "id": row.DocDocument.id,
            "title": row.DocDocument.title,
            "summary": row.DocDocument.summary or "",
            "category_name": row.cat_name,
            "db_type": row.cat_db_type,
        }
        for row in result.all()
    ]


async def get_document(db: AsyncSession, doc_id: int) -> DocDocument:
    result = await db.execute(select(DocDocument).where(DocDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


async def create_document(db: AsyncSession, data: DocDocumentCreate, user_id: int) -> DocDocument:
    summary = data.summary or auto_summary(data.content)
    doc = DocDocument(
        category_id=data.category_id,
        title=data.title,
        content=data.content,
        summary=summary,
        sort_order=data.sort_order,
        created_by=user_id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def update_document(db: AsyncSession, doc_id: int, data: DocDocumentUpdate) -> DocDocument:
    doc = await get_document(db, doc_id)
    update_data = data.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(doc, field, value)
    if 'content' in update_data and 'summary' not in update_data:
        doc.summary = auto_summary(update_data['content'])
    await db.commit()
    await db.refresh(doc)
    return doc


async def delete_document(db: AsyncSession, doc_id: int):
    doc = await get_document(db, doc_id)
    if doc.is_builtin:
        raise HTTPException(status_code=403, detail="内置文档不可删除")
    await db.delete(doc)
    await db.commit()
```

- [ ] **Step 2: 提交**

```bash
git add backend/services/document_service.py
git commit -m "feat: add document CRUD service with auto_summary"
```

---

## Task 4: REST API 路由

**Files:**
- Create: `backend/routers/documents.py`

- [ ] **Step 1: 实现路由**

```python
# backend/routers/documents.py
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.document import DocCategory, DocDocument
from backend.services import document_service
from backend.schemas.document import (
    DocCategoryResponse, DocCategoryCreate,
    DocDocumentCreate, DocDocumentUpdate,
    DocDocumentListItem, DocDocumentResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/docs",
    tags=["documents"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/categories", response_model=List[DocCategoryResponse])
async def get_categories(
    db_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    roots = await document_service.get_category_tree(db, db_type)
    response = []
    for cat in roots:
        children = getattr(cat, '_children', [])
        children_resp = []
        for ch in children:
            count_result = await db.execute(
                select(func.count(DocDocument.id))
                .where(DocDocument.category_id == ch.id, DocDocument.is_active == True)
            )
            ch_count = count_result.scalar() or 0
            children_resp.append(DocCategoryResponse.model_validate({
                **{c.key: getattr(ch, c.key) for c in ch.__table__.columns},
                "children": [], "document_count": ch_count,
            }))
        count_result = await db.execute(
            select(func.count(DocDocument.id))
            .where(DocDocument.category_id == cat.id, DocDocument.is_active == True)
        )
        cat_count = count_result.scalar() or 0
        response.append(DocCategoryResponse.model_validate({
            **{c.key: getattr(cat, c.key) for c in cat.__table__.columns},
            "children": children_resp, "document_count": cat_count,
        }))
    return response


@router.get("/categories/{category_id}/documents", response_model=List[DocDocumentListItem])
async def list_documents(category_id: int, db: AsyncSession = Depends(get_db)):
    return await document_service.list_documents_by_category(db, category_id)


@router.get("/{doc_id}/export")
async def export_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await document_service.get_document(db, doc_id)
    filename = doc.title.replace('/', '_') + ".md"
    return Response(
        content=doc.content.encode('utf-8'),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{doc_id}", response_model=DocDocumentResponse)
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    return await document_service.get_document(db, doc_id)


@router.post("", response_model=DocDocumentResponse)
async def create_document(
    data: DocDocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await document_service.create_document(db, data, current_user.id)


@router.put("/{doc_id}", response_model=DocDocumentResponse)
async def update_document(
    doc_id: int,
    data: DocDocumentUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await document_service.update_document(db, doc_id, data)


@router.delete("/{doc_id}")
async def delete_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    await document_service.delete_document(db, doc_id)
    return {"message": "文档已删除"}
```

注意：export 路由必须在 `/{doc_id}` 之前注册，避免路由冲突。

- [ ] **Step 2: 提交**

```bash
git add backend/routers/documents.py
git commit -m "feat: add document REST API router"
```

---

## Task 5: 内置文档种子数据 - MySQL

**Files:**
- Create: `backend/services/builtin_docs/__init__.py`
- Create: `backend/services/builtin_docs/mysql_docs.py`

- [ ] **Step 1: 创建 `__init__.py`（空文件）**

- [ ] **Step 2: 创建 mysql_docs.py**

`MYSQL_DOCS` 是一个列表，每项包含 `category`、`title`、`content`（完整 Markdown）。

20 篇文档的 category 和 title：
```
综合诊断: MySQL 数据库综合诊断流程
性能诊断: MySQL CPU使用高诊断优化流程
性能诊断: MySQL 空间占用高诊断优化流程
性能诊断: MySQL 网络流量高诊断优化流程
性能诊断: MySQL SQL诊断优化流程
性能诊断: MySQL 写入慢诊断优化流程
性能诊断: MySQL 索引优化诊断流程
故障排查: MySQL 死锁诊断优化流程
故障排查: MySQL 连接失败诊断流程
故障排查: MySQL SQL执行失败诊断流程
故障排查: MySQL 主备延时诊断流程
故障排查: MySQL 主备数据不一致诊断流程
故障排查: MySQL 启动失败诊断流程
故障排查: MySQL 数据丢失恢复方案
配置与会话: MySQL 系统参数配置诊断优化流程
配置与会话: MySQL 会话连接诊断优化流程
安全与权限: MySQL 安全诊断方案
安全与权限: MySQL 用户权限诊断方案
技术参考: MySQL binlog技术细节
技术参考: MySQL 错误码查询
```

每篇文档要求：
- 800~5000 字，内容专业准确
- 诊断步骤结构化（使用 Markdown 标题/列表/代码块）
- 明确写明调用哪个 skill（如「调用 `get_process_list` skill 获取当前连接列表」）
- 包含具体 SQL 示例
- skill 名称从以下列表选取：`get_db_status`, `get_db_variables`, `get_process_list`, `get_slow_queries`, `get_table_stats`, `get_replication_status`, `get_db_size`, `execute_diagnostic_query`, `explain_query`, `get_os_metrics`, `execute_os_command`, `get_metric_history`, `list_connections`

- [ ] **Step 3: 提交**

```bash
git add backend/services/builtin_docs/
git commit -m "feat: add MySQL builtin docs (20 docs)"
```

---

## Task 6: 内置文档种子数据 - PostgreSQL、Oracle、SQL Server

**Files:**
- Create: `backend/services/builtin_docs/postgresql_docs.py`
- Create: `backend/services/builtin_docs/oracle_docs.py`
- Create: `backend/services/builtin_docs/sqlserver_docs.py`

每个文件包含对应数据库的 20 篇文档，分类结构与 MySQL 相同，内容针对各数据库特性定制。

PostgreSQL 特有关注点：pg_stat_activity、pg_locks、autovacuum、WAL、pg_dump
Oracle 特有关注点：AWR/ASH、执行计划、RAC、undo tablespace、归档日志
SQL Server 特有关注点：DMV、执行计划、AlwaysOn、tempdb、等待统计

- [ ] **Step 1: 创建 postgresql_docs.py**（POSTGRESQL_DOCS 列表，20篇）
- [ ] **Step 2: 创建 oracle_docs.py**（ORACLE_DOCS 列表，20篇）
- [ ] **Step 3: 创建 sqlserver_docs.py**（SQLSERVER_DOCS 列表，20篇）

- [ ] **Step 4: 提交**

```bash
git add backend/services/builtin_docs/
git commit -m "feat: add PostgreSQL/Oracle/SQLServer builtin docs"
```

---

## Task 7: 种子写入逻辑

**Files:**
- Create: `backend/services/builtin_docs/seeder.py`

- [ ] **Step 1: 实现 seeder.py**

```python
# backend/services/builtin_docs/seeder.py
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.document import DocCategory, DocDocument
from backend.services.document_service import auto_summary
from backend.services.builtin_docs.mysql_docs import MYSQL_DOCS
from backend.services.builtin_docs.postgresql_docs import POSTGRESQL_DOCS
from backend.services.builtin_docs.oracle_docs import ORACLE_DOCS
from backend.services.builtin_docs.sqlserver_docs import SQLSERVER_DOCS

logger = logging.getLogger(__name__)

# 分类结构定义（一级=db类型, 二级=场景）
DB_TYPES = [
    {"db_type": "mysql",      "name": "MySQL"},
    {"db_type": "postgresql", "name": "PostgreSQL"},
    {"db_type": "oracle",     "name": "Oracle"},
    {"db_type": "sqlserver",  "name": "SQL Server"},
]

SCENARIO_CATEGORIES = [
    "综合诊断", "性能诊断", "故障排查", "配置与会话", "安全与权限", "技术参考"
]

DOCS_MAP = {
    "mysql":      MYSQL_DOCS,
    "postgresql": POSTGRESQL_DOCS,
    "oracle":     ORACLE_DOCS,
    "sqlserver":  SQLSERVER_DOCS,
}


async def seed_builtin_docs(db: AsyncSession):
    """启动时写入内置文档，已存在则跳过（按 title + category 判断）"""
    # 检查是否已初始化（存在任何内置文档）
    existing = await db.execute(
        select(DocDocument).where(DocDocument.is_builtin == True).limit(1)
    )
    if existing.scalar_one_or_none():
        logger.info("Builtin docs already seeded, skipping.")
        return

    logger.info("Seeding builtin docs...")
    category_map = {}  # (db_type, scenario_name) -> category_id

    # 创建一级分类（db 类型）和二级分类（场景）
    for sort_i, db_type_def in enumerate(DB_TYPES):
        db_type = db_type_def["db_type"]
        root_cat = DocCategory(
            name=db_type_def["name"],
            db_type=db_type,
            parent_id=None,
            sort_order=sort_i,
        )
        db.add(root_cat)
        await db.flush()  # 获取 root_cat.id

        for sort_j, scenario in enumerate(SCENARIO_CATEGORIES):
            child_cat = DocCategory(
                name=scenario,
                db_type=db_type,
                parent_id=root_cat.id,
                sort_order=sort_j,
            )
            db.add(child_cat)
            await db.flush()
            category_map[(db_type, scenario)] = child_cat.id

    # 写入文档
    doc_count = 0
    for db_type, docs in DOCS_MAP.items():
        for sort_k, doc_def in enumerate(docs):
            cat_id = category_map.get((db_type, doc_def["category"]))
            if not cat_id:
                logger.warning(f"Unknown category: {doc_def['category']} for {db_type}")
                continue
            content = doc_def["content"]
            doc = DocDocument(
                category_id=cat_id,
                title=doc_def["title"],
                content=content,
                summary=auto_summary(content),
                is_builtin=True,
                is_active=True,
                sort_order=sort_k,
            )
            db.add(doc)
            doc_count += 1

    await db.commit()
    logger.info(f"Seeded {doc_count} builtin docs successfully.")
```

- [ ] **Step 2: 提交**

```bash
git add backend/services/builtin_docs/seeder.py
git commit -m "feat: add builtin docs seeder"
```

---

## Task 8: 迁移脚本

**Files:**
- Create: `backend/migrations/replace_knowledge_base_with_documents.py`

- [ ] **Step 1: 实现迁移脚本**

```python
# backend/migrations/replace_knowledge_base_with_documents.py
import logging
from sqlalchemy import text
from backend.database import async_session

logger = logging.getLogger(__name__)


async def migrate():
    """删除旧知识库表（如存在），新表由 SQLAlchemy create_all 自动创建"""
    async with async_session() as db:
        for table in ["knowledge_chunks", "documents", "knowledge_bases"]:
            try:
                await db.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                logger.info(f"Dropped table: {table}")
            except Exception as e:
                logger.warning(f"Could not drop {table}: {e}")
        await db.commit()
```

- [ ] **Step 2: 提交**

```bash
git add backend/migrations/replace_knowledge_base_with_documents.py
git commit -m "feat: add migration to drop old knowledge base tables"
```

---

## Task 9: 更新后端核心文件

**Files:**
- Modify: `backend/models/document.py`（在 database.py 的 init_db 中注册）
- Modify: `backend/database.py`
- Modify: `backend/app.py`
- Modify: `backend/config.py`

- [ ] **Step 1: 更新 database.py**

在 `init_db()` 中：
- 将 `import backend.models.knowledge_base` 替换为 `import backend.models.document`
- 在 `load_builtin_skills` 之后添加种子调用：

```python
# 在 init_db() 末尾添加
from backend.services.builtin_docs.seeder import seed_builtin_docs
async with async_session() as session:
    await seed_builtin_docs(session)
```

- [ ] **Step 2: 更新 app.py**

a. 删除 KB processor 全局变量和 lifespan 中的 KB 初始化代码（约第 14 行 `kb_processor = None` 及 lifespan 中的相关块）

b. 在 lifespan 中添加迁移调用：
```python
try:
    from backend.migrations.replace_knowledge_base_with_documents import migrate as migrate_docs
    await migrate_docs()
except Exception as e:
    logger.warning(f"Document migration: {e}")
```

c. 替换路由注册：
```python
# 删除
from backend.routers import ... knowledge_bases ...
app.include_router(knowledge_bases.router)

# 新增
from backend.routers import documents
app.include_router(documents.router)
```

- [ ] **Step 3: 更新 config.py**

删除以下配置项：
```python
chroma_persist_dir: str = "./data/chroma"
embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
knowledge_base_dir: str = "./data/knowledge_bases"
```

- [ ] **Step 4: 提交**

```bash
git add backend/database.py backend/app.py backend/config.py
git commit -m "feat: integrate document module into app lifecycle"
```

---

## Task 10: 更新 AI 工具

**Files:**
- Modify: `backend/agent/context_builder.py`

- [ ] **Step 1: 替换 search_knowledge_base 工具**

在 `_dispatch_tool` 的 handlers dict 中：
```python
# 删除
"search_knowledge_base": _tool_search_knowledge_base,

# 新增
"list_documents": _tool_list_documents,
"read_document": _tool_read_document,
```

- [ ] **Step 2: 实现两个新工具函数**

```python
async def _tool_list_documents(args):
    """列出文档目录，供 AI 决策读哪篇文档"""
    db_type = args.get("db_type")  # 可选，按数据库类型过滤
    from backend.database import async_session
    from backend.services.document_service import list_documents_for_ai
    async with async_session() as db:
        return await list_documents_for_ai(db, db_type)


async def _tool_read_document(args):
    """读取指定文档完整内容"""
    doc_id = args.get("doc_id")
    if not doc_id:
        return {"error": "doc_id is required"}
    from backend.database import async_session
    from backend.models.document import DocDocument, DocCategory
    from sqlalchemy import select
    async with async_session() as db:
        result = await db.execute(
            select(DocDocument, DocCategory.name.label("cat_name"))
            .join(DocCategory, DocDocument.category_id == DocCategory.id)
            .where(DocDocument.id == doc_id, DocDocument.is_active == True)
        )
        row = result.one_or_none()
        if not row:
            return {"error": f"Document {doc_id} not found"}
        doc, cat_name = row.DocDocument, row.cat_name
        return {
            "id": doc.id,
            "title": doc.title,
            "category_name": cat_name,
            "content": doc.content,
        }
```

- [ ] **Step 3: 删除旧的 `_tool_search_knowledge_base` 函数**

- [ ] **Step 4: 提交**

```bash
git add backend/agent/context_builder.py
git commit -m "feat: replace search_knowledge_base with list_documents/read_document tools"
```

---

## Task 11: 更新 AI 工具定义（tools schema）

**Files:**
- Modify: `backend/agent/tools.py`（如存在）或 `backend/agent/conversation_skills.py`

- [ ] **Step 1: 找到工具 schema 定义位置**

运行：`grep -n "search_knowledge_base" backend/agent/tools.py backend/agent/conversation_skills.py backend/agent/skill_selector.py`

- [ ] **Step 2: 替换 search_knowledge_base 的工具定义**

删除 `search_knowledge_base` 的工具 schema，新增：

```python
{
    "type": "function",
    "function": {
        "name": "list_documents",
        "description": "列出知识库中的诊断文档目录（含摘要），AI 根据目录决定需要读取哪些文档。可按数据库类型过滤。",
        "parameters": {
            "type": "object",
            "properties": {
                "db_type": {
                    "type": "string",
                    "description": "数据库类型过滤，可选值: mysql, postgresql, oracle, sqlserver，不传则返回所有类型"
                }
            }
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "read_document",
        "description": "读取指定文档的完整 Markdown 内容。根据 list_documents 返回的文档目录选择合适的文档 id 后调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "integer",
                    "description": "文档 ID，从 list_documents 返回的列表中获取"
                }
            },
            "required": ["doc_id"]
        }
    }
}
```

- [ ] **Step 3: 提交**

```bash
git add backend/agent/
git commit -m "feat: update AI tool schema for document tools"
```

---

## Task 12: 删除旧代码文件

**Files:**
- Delete: `backend/models/knowledge_base.py`
- Delete: `backend/schemas/knowledge_base.py`
- Delete: `backend/routers/knowledge_bases.py`
- Delete: `backend/services/vector_store.py`
- Delete: `backend/services/document_chunker.py`
- Delete: `backend/services/document_parser.py`
- Delete: `backend/utils/embeddings.py`

- [ ] **Step 1: 删除旧后端文件**

```bash
rm backend/models/knowledge_base.py
rm backend/schemas/knowledge_base.py
rm backend/routers/knowledge_bases.py
rm backend/services/vector_store.py
rm backend/services/document_chunker.py
rm backend/services/document_parser.py
rm backend/utils/embeddings.py
```

- [ ] **Step 2: 检查是否有其他文件引用了旧模块**

```bash
grep -r "knowledge_base\|vector_store\|document_chunker\|document_parser\|embeddings" backend/ --include="*.py" -l
```

修复所有残留引用。

- [ ] **Step 3: 更新 requirements.txt**

移除：
```
chromadb
sentence-transformers
```
（如果 torch 仅为 embedding 使用，也可移除）

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "chore: remove old knowledge base files and ChromaDB dependencies"
```

---

## Task 13: 前端 API 更新

**Files:**
- Modify: `frontend/js/api.js`

- [ ] **Step 1: 替换 KB 相关 API 方法**

找到 `api.js` 中第 230-265 行的 KB 方法，全部替换为：

```javascript
// Document API
getDocCategories(dbType = null) {
    const qs = dbType ? `?db_type=${dbType}` : '';
    return this.get(`/api/docs/categories${qs}`);
},
getCategoryDocuments(categoryId) {
    return this.get(`/api/docs/categories/${categoryId}/documents`);
},
getDocument(docId) {
    return this.get(`/api/docs/${docId}`);
},
createDocument(data) {
    return this.post('/api/docs', data);
},
updateDocument(docId, data) {
    return this.put(`/api/docs/${docId}`, data);
},
deleteDocument(docId) {
    return this.delete(`/api/docs/${docId}`);
},
exportDocument(docId) {
    const token = localStorage.getItem('auth_token');
    const a = document.createElement('a');
    a.href = `/api/docs/${docId}/export`;
    a.click();
},
async importDocument(categoryId, title, markdownContent) {
    return this.post('/api/docs', {
        category_id: categoryId,
        title: title,
        content: markdownContent,
    });
},
```

- [ ] **Step 2: 提交**

```bash
git add frontend/js/api.js
git commit -m "feat: update frontend API for document module"
```

---

## Task 14: 前端页面 - documents.js

**Files:**
- Create: `frontend/js/pages/documents.js`
- Delete: `frontend/js/pages/knowledge-bases.js`

页面布局：三栏（分类树 + 文档列表 + Monaco 编辑器/预览）

- [ ] **Step 1: 实现 documents.js**

```javascript
/* Documents page - 知识库文档管理 */
const DocumentsPage = {
    currentCategory: null,
    currentDoc: null,
    monacoEditor: null,
    mdRenderer: null,
    viewMode: 'split', // 'split' | 'edit' | 'preview'

    async render() {
        const content = DOM.$('#page-content');
        Header.render('知识库文档');
        content.innerHTML = `
            <div class="docs-layout">
                <div class="docs-sidebar" id="docs-categories"></div>
                <div class="docs-list" id="docs-list"></div>
                <div class="docs-editor" id="docs-editor-panel">
                    <div class="docs-editor-placeholder">
                        <i data-lucide="file-text" style="width:48px;height:48px"></i>
                        <p>选择文档进行查看或编辑</p>
                    </div>
                </div>
            </div>
        `;
        DOM.createIcons();
        this.mdRenderer = window.markdownit ? window.markdownit() : null;
        await this.loadCategories();
    },

    async loadCategories() {
        try {
            const categories = await API.getDocCategories();
            const container = DOM.$('#docs-categories');
            container.innerHTML = `<div class="docs-cat-header">分类</div>`;
            categories.forEach((root, i) => {
                const rootEl = DOM.el('div', { className: 'docs-cat-root' });
                rootEl.innerHTML = `
                    <div class="docs-cat-root-name" data-idx="${i}">
                        <i data-lucide="database"></i> ${Utils.escapeHtml(root.name)}
                        <i data-lucide="chevron-down" class="chevron"></i>
                    </div>
                    <div class="docs-cat-children" id="cat-children-${i}">
                        ${(root.children || []).map(ch => `
                            <div class="docs-cat-child" data-cat-id="${ch.id}" data-cat-name="${Utils.escapeHtml(ch.name)}">
                                ${Utils.escapeHtml(ch.name)}
                                <span class="docs-cat-count">${ch.document_count}</span>
                            </div>
                        `).join('')}
                    </div>
                `;
                container.appendChild(rootEl);
                rootEl.querySelector('.docs-cat-root-name').addEventListener('click', () => {
                    rootEl.querySelector('.docs-cat-children').classList.toggle('hidden');
                });
                rootEl.querySelectorAll('.docs-cat-child').forEach(el => {
                    el.addEventListener('click', () => this.selectCategory(el));
                });
            });
            DOM.createIcons();
        } catch (e) {
            Utils.showToast('加载分类失败: ' + e.message, 'error');
        }
    },

    async selectCategory(el) {
        DOM.$$('.docs-cat-child').forEach(e => e.classList.remove('active'));
        el.classList.add('active');
        this.currentCategory = { id: +el.dataset.catId, name: el.dataset.catName };
        await this.loadDocList(this.currentCategory.id);
    },

    async loadDocList(categoryId) {
        const container = DOM.$('#docs-list');
        container.innerHTML = '<div class="loading">加载中...</div>';
        try {
            const docs = await API.getCategoryDocuments(categoryId);
            container.innerHTML = `
                <div class="docs-list-header">
                    <span>${this.currentCategory?.name || ''}</span>
                    <button class="btn btn-sm btn-primary" onclick="DocumentsPage.newDocument()">
                        <i data-lucide="plus"></i> 新建
                    </button>
                </div>
            `;
            if (docs.length === 0) {
                container.innerHTML += '<div class="empty-state"><p>暂无文档</p></div>';
            } else {
                docs.forEach(doc => {
                    const el = DOM.el('div', { className: 'docs-list-item' });
                    el.dataset.docId = doc.id;
                    el.innerHTML = `
                        <div class="docs-list-item-title">
                            ${doc.is_builtin ? '<i data-lucide="lock" class="builtin-icon"></i>' : ''}
                            ${Utils.escapeHtml(doc.title)}
                        </div>
                        <div class="docs-list-item-summary">${Utils.escapeHtml(doc.summary || '')}</div>
                    `;
                    el.addEventListener('click', () => this.openDocument(doc.id, el));
                    container.appendChild(el);
                });
            }
            DOM.createIcons();
        } catch (e) {
            Utils.showToast('加载文档列表失败: ' + e.message, 'error');
        }
    },

    async openDocument(docId, listEl) {
        DOM.$$('.docs-list-item').forEach(e => e.classList.remove('active'));
        if (listEl) listEl.classList.add('active');
        try {
            const doc = await API.getDocument(docId);
            this.currentDoc = doc;
            this.renderEditor(doc);
        } catch (e) {
            Utils.showToast('加载文档失败: ' + e.message, 'error');
        }
    },

    renderEditor(doc) {
        const panel = DOM.$('#docs-editor-panel');
        panel.innerHTML = `
            <div class="docs-editor-toolbar">
                <span class="docs-editor-title">${Utils.escapeHtml(doc.title)}</span>
                <div class="docs-editor-actions">
                    <button class="btn btn-sm" onclick="DocumentsPage.setViewMode('edit')" id="btn-edit-mode">编辑</button>
                    <button class="btn btn-sm" onclick="DocumentsPage.setViewMode('split')" id="btn-split-mode">分栏</button>
                    <button class="btn btn-sm" onclick="DocumentsPage.setViewMode('preview')" id="btn-preview-mode">预览</button>
                    <button class="btn btn-sm btn-primary" onclick="DocumentsPage.saveDocument()">保存</button>
                    <button class="btn btn-sm" onclick="DocumentsPage.exportDocument(${doc.id})">导出</button>
                    ${!doc.is_builtin ? `<button class="btn btn-sm btn-danger" onclick="DocumentsPage.deleteDocument(${doc.id})">删除</button>` : ''}
                </div>
            </div>
            <div class="docs-editor-body" id="docs-editor-body">
                <div class="docs-monaco-container" id="docs-monaco"></div>
                <div class="docs-preview-container" id="docs-preview"></div>
            </div>
        `;
        this.initMonaco(doc.content);
        this.setViewMode(this.viewMode);
    },

    initMonaco(content) {
        if (this.monacoEditor) {
            this.monacoEditor.dispose();
            this.monacoEditor = null;
        }
        require.config({ paths: { vs: '/lib/monaco-editor/min/vs' } });
        require(['vs/editor/editor.main'], () => {
            const container = DOM.$('#docs-monaco');
            if (!container) return;
            this.monacoEditor = monaco.editor.create(container, {
                value: content,
                language: 'markdown',
                theme: document.body.classList.contains('dark') ? 'vs-dark' : 'vs',
                wordWrap: 'on',
                minimap: { enabled: false },
                lineNumbers: 'off',
                fontSize: 14,
                scrollBeyondLastLine: false,
            });
            this.monacoEditor.onDidChangeModelContent(() => this.updatePreview());
            this.updatePreview();
        });
    },

    updatePreview() {
        const preview = DOM.$('#docs-preview');
        if (!preview || !this.monacoEditor) return;
        const md = this.monacoEditor.getValue();
        if (this.mdRenderer) {
            preview.innerHTML = this.mdRenderer.render(md);
        } else {
            preview.innerHTML = `<pre>${Utils.escapeHtml(md)}</pre>`;
        }
    },

    setViewMode(mode) {
        this.viewMode = mode;
        const monacoEl = DOM.$('#docs-monaco');
        const previewEl = DOM.$('#docs-preview');
        if (!monacoEl || !previewEl) return;
        if (mode === 'edit') {
            monacoEl.style.display = 'flex';
            monacoEl.style.width = '100%';
            previewEl.style.display = 'none';
        } else if (mode === 'preview') {
            monacoEl.style.display = 'none';
            previewEl.style.display = 'block';
            previewEl.style.width = '100%';
            this.updatePreview();
        } else { // split
            monacoEl.style.display = 'flex';
            monacoEl.style.width = '50%';
            previewEl.style.display = 'block';
            previewEl.style.width = '50%';
            this.updatePreview();
        }
        if (this.monacoEditor) this.monacoEditor.layout();
    },

    async saveDocument() {
        if (!this.currentDoc || !this.monacoEditor) return;
        const content = this.monacoEditor.getValue();
        try {
            await API.updateDocument(this.currentDoc.id, { content });
            Utils.showToast('保存成功', 'success');
            // 刷新列表（summary 可能已更新）
            if (this.currentCategory) await this.loadDocList(this.currentCategory.id);
        } catch (e) {
            Utils.showToast('保存失败: ' + e.message, 'error');
        }
    },

    exportDocument(docId) {
        API.exportDocument(docId);
    },

    async deleteDocument(docId) {
        if (!confirm('确认删除此文档？此操作不可恢复。')) return;
        try {
            await API.deleteDocument(docId);
            Utils.showToast('文档已删除', 'success');
            DOM.$('#docs-editor-panel').innerHTML = '<div class="docs-editor-placeholder"><p>请选择文档</p></div>';
            this.currentDoc = null;
            if (this.currentCategory) await this.loadDocList(this.currentCategory.id);
        } catch (e) {
            Utils.showToast('删除失败: ' + e.message, 'error');
        }

    async newDocument() {
        if (!this.currentCategory) {
            Utils.showToast('请先选择分类', 'warning');
            return;
        }
        Modal.show({
            title: '新建文档',
            content: `
                <div class="form-group">
                    <label>文档标题</label>
                    <input type="text" id="new-doc-title" class="form-control" placeholder="文档标题">
                </div>
            `,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '创建', variant: 'primary', onClick: async () => {
                    const title = DOM.$('#new-doc-title').value.trim();
                    if (!title) return;
                    try {
                        const doc = await API.createDocument({
                            category_id: this.currentCategory.id,
                            title,
                            content: `# ${title}\n\n`,
                        });
                        Modal.hide();
                        await this.loadDocList(this.currentCategory.id);
                        await this.openDocument(doc.id);
                    } catch (e) {
                        Utils.showToast('创建失败: ' + e.message, 'error');
                    }
                }}
            ]
        });
    },
};
```

- [ ] **Step 2: 删除旧文件**

```bash
rm frontend/js/pages/knowledge-bases.js
```

- [ ] **Step 3: 提交**

```bash
git add frontend/js/pages/documents.js
git rm frontend/js/pages/knowledge-bases.js
git commit -m "feat: add documents page with Monaco editor and split preview"
```

---

## Task 15: 更新 index.html 和路由

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: 替换脚本引用**

将：
```html
<script src="/js/pages/knowledge-bases.js"></script>
```
替换为：
```html
<script src="/js/pages/documents.js"></script>
```

- [ ] **Step 2: 更新侧边栏导航（如在 sidebar.js 或 index.html 中定义）**

找到 `knowledge-bases` 路由，改为 `documents`；导航名称改为「知识库」，保持图标不变。

- [ ] **Step 3: 更新路由注册（app.js 或 router 初始化处）**

找到路由注册代码：
```javascript
Router.register('knowledge-bases', () => KnowledgeBasesPage.render());
```
替换为：
```javascript
Router.register('documents', () => DocumentsPage.render());
```

- [ ] **Step 4: 添加 CSS 文件引用**

在 index.html CSS 区域添加：
```html
<link rel="stylesheet" href="/css/documents.css">
```

- [ ] **Step 5: 提交**

```bash
git add frontend/index.html
git commit -m "feat: update routing for documents page"
```

---

## Task 16: 前端 CSS

**Files:**
- Create: `frontend/css/documents.css`

- [ ] **Step 1: 创建 documents.css**

```css
/* Documents Page Layout */
.docs-layout {
    display: flex;
    height: calc(100vh - 60px);
    overflow: hidden;
    gap: 0;
}

.docs-sidebar {
    width: 200px;
    min-width: 160px;
    border-right: 1px solid var(--border-color);
    overflow-y: auto;
    padding: 8px 0;
    flex-shrink: 0;
}

.docs-cat-header {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--text-muted);
    padding: 4px 12px 8px;
    letter-spacing: 0.05em;
}

.docs-cat-root-name {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    font-weight: 500;
    cursor: pointer;
    color: var(--text-primary);
    user-select: none;
}
.docs-cat-root-name:hover { background: var(--bg-hover); }
.docs-cat-root-name .chevron { margin-left: auto; width: 14px; height: 14px; }

.docs-cat-child {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 5px 12px 5px 28px;
    font-size: 13px;
    cursor: pointer;
    color: var(--text-secondary);
    border-radius: 4px;
    margin: 1px 6px;
}
.docs-cat-child:hover { background: var(--bg-hover); color: var(--text-primary); }
.docs-cat-child.active { background: var(--primary-light); color: var(--primary); font-weight: 500; }
.docs-cat-count {
    font-size: 11px;
    background: var(--bg-secondary);
    padding: 1px 6px;
    border-radius: 10px;
    color: var(--text-muted);
}
.docs-cat-children.hidden { display: none; }

/* Doc List */
.docs-list {
    width: 260px;
    min-width: 200px;
    border-right: 1px solid var(--border-color);
    overflow-y: auto;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
}
.docs-list-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    font-weight: 500;
    font-size: 13px;
    border-bottom: 1px solid var(--border-color);
    position: sticky;
    top: 0;
    background: var(--bg-primary);
    z-index: 1;
}
.docs-list-item {
    padding: 10px 12px;
    cursor: pointer;
    border-bottom: 1px solid var(--border-color-light);
}
.docs-list-item:hover { background: var(--bg-hover); }
.docs-list-item.active { background: var(--primary-light); }
.docs-list-item-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
}
.docs-list-item-summary {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.4;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}
.builtin-icon { width: 12px; height: 12px; color: var(--text-muted); }

/* Editor Panel */
.docs-editor {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}
.docs-editor-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-muted);
    gap: 12px;
}
.docs-editor-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
}
.docs-editor-title {
    font-weight: 500;
    font-size: 14px;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 300px;
}
.docs-editor-actions { display: flex; gap: 6px; align-items: center; }
.docs-editor-body {
    flex: 1;
    display: flex;
    overflow: hidden;
}
.docs-monaco-container {
    flex: 1;
    overflow: hidden;
    display: flex;
}
.docs-preview-container {
    overflow-y: auto;
    padding: 20px 24px;
    border-left: 1px solid var(--border-color);
    line-height: 1.7;
    font-size: 14px;
    color: var(--text-primary);
}
.docs-preview-container h1, .docs-preview-container h2, .docs-preview-container h3 {
    margin-top: 1.2em;
    margin-bottom: 0.5em;
}
.docs-preview-container code {
    background: var(--bg-secondary);
    padding: 2px 5px;
    border-radius: 3px;
    font-family: var(--font-mono);
    font-size: 13px;
}
.docs-preview-container pre {
    background: var(--bg-secondary);
    padding: 12px 16px;
    border-radius: 6px;
    overflow-x: auto;
}
.docs-preview-container table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
}
.docs-preview-container th, .docs-preview-container td {
    border: 1px solid var(--border-color);
    padding: 6px 12px;
    text-align: left;
}
.docs-preview-container th { background: var(--bg-secondary); font-weight: 600; }
```

- [ ] **Step 2: 提交**

```bash
git add frontend/css/documents.css
git commit -m "feat: add documents page CSS"
```

---

## Task 17: 启动验证

- [ ] **Step 1: 启动后端**

```bash
python run.py
```

预期：
- 无 import 错误
- 日志显示 `Seeded 80 builtin docs successfully`
- 迁移日志显示删除旧表成功

- [ ] **Step 2: 验证 API**

```bash
# 获取分类树
curl -s http://localhost:9939/api/docs/categories -H "Authorization: Bearer <token>" | python -m json.tool

# 读取第一篇文档
curl -s http://localhost:9939/api/docs/1 -H "Authorization: Bearer <token>" | python -m json.tool
```

- [ ] **Step 3: 验证前端**

打开浏览器访问 `http://localhost:9939`，导航到「知识库」：
- 左侧显示 MySQL/PostgreSQL/Oracle/SQL Server 分类树
- 点击子分类后中间显示文档列表
- 点击文档后右侧显示 Monaco 编辑器和预览
- 分栏/编辑/预览三种模式正常切换
- 内置文档标有锁图标，无删除按钮

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat: knowledge base module redesign complete"
```
