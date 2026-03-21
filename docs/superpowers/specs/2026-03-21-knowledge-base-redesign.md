# 知识库模块重设计方案

**日期**: 2026-03-21
**状态**: 已确认
**作者**: 头脑风暴会话

---

## 背景与目标

现有知识库模块基于 ChromaDB + 向量嵌入（RAG）技术，存在以下问题：
- 向量检索只能返回语义相关片段，AI 缺乏完整上下文
- ChromaDB 依赖重，部署复杂
- 文档分块破坏了诊断流程文档的完整性和可操作性

**新方案目标**：AI 诊断时按需读取完整 Markdown 文档，根据文档内容决策后续 skill 调用，彻底移除向量技术。

---

## 核心架构

### AI 文档访问流程

```
用户提问
  → AI 收到系统 context（含当前数据源类型）
  → AI 调用 list_documents(db_type) 获取文档目录（id + title + summary）
  → AI 选择相关文档调用 read_document(doc_id) 读取完整 Markdown 全文
  → AI 结合文档内容 + 数据库实时指标 + skills 执行诊断
```

### 关键设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 文档检索方式 | AI 主动选择（目录+工具） | AI 自主判断需要哪些文档，比关键词匹配更智能 |
| 分类体系 | 两级：数据库类型 > 诊断场景 | 与 datasource.db_type 对齐，AI 可精准过滤 |
| 内容存储 | PostgreSQL Text 字段为主 | 无磁盘文件管理复杂性，支持导入/导出 |
| 编辑器 | Monaco Editor（CDN）+ marked 预览 | 专业代码编辑体验，无需构建步骤 |
| 旧表处理 | 完全删除旧表和相关代码 | 干净替换，无历史包袱 |

---

## 数据库设计

### 删除旧表
- `knowledge_bases`
- `documents`
- `knowledge_chunks`

### 新建表

```sql
-- 文档分类表（两级）
CREATE TABLE doc_categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    db_type     VARCHAR(50) NOT NULL,  -- mysql/postgresql/oracle/sqlserver/general
    parent_id   INTEGER REFERENCES doc_categories(id),  -- NULL = 一级分类
    sort_order  INTEGER DEFAULT 0,
    icon        VARCHAR(50),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 文档主表
CREATE TABLE doc_documents (
    id          SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES doc_categories(id),
    title       VARCHAR(200) NOT NULL,
    content     TEXT NOT NULL,           -- 完整 Markdown 内容
    summary     TEXT,                   -- 100字内摘要，AI 目录使用
    is_builtin  BOOLEAN DEFAULT FALSE,  -- 内置文档不可删除
    is_active   BOOLEAN DEFAULT TRUE,
    sort_order  INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW(),
    created_by  INTEGER                 -- user id，内置文档为 NULL
);
```

---

## 后端实现

### 删除文件
- `backend/services/vector_store.py`
- `backend/services/document_chunker.py`
- `backend/services/document_parser.py`
- `backend/utils/embeddings.py`
- `backend/models/knowledge_base.py`
- `backend/routers/knowledge_bases.py`
- `backend/schemas/knowledge_base.py`

### 新增文件

```
backend/models/document.py          # DocCategory, DocDocument SQLAlchemy 模型
backend/schemas/document.py         # Pydantic schemas
backend/services/document_service.py # CRUD 业务逻辑 + 导入导出
backend/services/builtin_docs/
    __init__.py
    seeder.py                        # 种子数据写入逻辑（启动时调用）
    mysql_docs.py                    # MySQL 20篇内置文档内容
    postgresql_docs.py               # PostgreSQL 20篇
    oracle_docs.py                   # Oracle 20篇
    sqlserver_docs.py                # SQL Server 20篇
backend/routers/documents.py        # REST API 路由
```

### REST API

```
GET    /api/docs/categories                    # 返回分类树（含 db_type 过滤）
GET    /api/docs/categories/{id}/documents     # 某分类文档列表（id+title+summary，不含全文）
GET    /api/docs/{id}                          # 文档详情（含完整 content）
POST   /api/docs                               # 新建文档
PUT    /api/docs/{id}                          # 编辑文档（is_builtin 文档允许编辑内容）
DELETE /api/docs/{id}                          # 删除（is_builtin=True 时返回 403）
GET    /api/docs/{id}/export                   # 导出为 .md 文件下载
POST   /api/docs/import                        # 上传 .md 文件导入
```

### AI 工具替换

在 `backend/agent/context_builder.py` 中：

**删除**：`search_knowledge_base` 工具

**新增两个工具**：

```python
list_documents(db_type: str = None, category_id: int = None) -> list
# 返回文档目录：[{id, title, category_name, db_type, summary}]
# AI 据此判断需要读取哪些文档

read_document(doc_id: int) -> dict
# 返回完整文档：{id, title, content (完整 Markdown), category_name, db_type}
# AI 按需调取，可多次调用
```

---

## 内置文档体系

### 文档总量：80 篇（4 数据库 × 20 篇）

### 分类结构（以 MySQL 为例，其余数据库同结构）

```
MySQL（db_type=mysql）
├── 综合诊断
│   └── MySQL 数据库综合诊断流程
├── 性能诊断
│   ├── MySQL CPU使用高诊断优化流程
│   ├── MySQL 空间占用高诊断优化流程
│   ├── MySQL 网络流量高诊断优化流程
│   ├── MySQL SQL诊断优化流程
│   ├── MySQL 写入慢诊断优化流程
│   └── MySQL 索引优化诊断流程
├── 故障排查
│   ├── MySQL 死锁诊断优化流程
│   ├── MySQL 连接失败诊断流程
│   ├── MySQL SQL执行失败诊断流程
│   ├── MySQL 主备延时诊断流程
│   ├── MySQL 主备数据不一致诊断流程
│   ├── MySQL 启动失败诊断流程
│   └── MySQL 数据丢失恢复方案
├── 配置与会话
│   ├── MySQL 系统参数配置诊断优化流程
│   └── MySQL 会话连接诊断优化流程
├── 安全与权限
│   ├── MySQL 安全诊断方案
│   └── MySQL 用户权限诊断方案
└── 技术参考
    ├── MySQL binlog技术细节
    └── MySQL 错误码查询
```

### 内置文档质量要求
- 每篇文档包含：问题现象描述、诊断步骤（含具体 SQL/命令）、可直接调用的 skill 名称、优化建议
- 文档明确写明调用哪个 skill（如「调用 `get_process_list` skill 获取当前连接列表」）
- 诊断步骤结构化，使用 Markdown 标题/列表/代码块
- 每篇文档 800~3000 字，内容专业准确

---

## 前端设计

### 页面布局（三栏）

```
┌─────────────┬──────────────────┬──────────────────────────────┐
│  分类树     │  文档列表        │  Monaco 编辑器 + 预览        │
│  (左侧)     │  (中间)          │  (右侧)                      │
│  180px      │  260px           │  flex: 1                     │
│             │                  │                              │
│  ▼ MySQL    │  ■ 综合诊断流程  │  [Edit] [Preview]  [保存]    │
│    性能诊断 │  ■ CPU使用高    │  ─────────────────────────── │
│    故障排查 │  ■ 空间占用高   │  Monaco Editor (左)          │
│  ▼ PgSQL    │  ...             │  Markdown Preview (右)       │
│  ▼ Oracle   │  [+ 新建文档]    │  （split 模式）              │
│  ▼ SQLSvr   │                  │                              │
└─────────────┴──────────────────┴──────────────────────────────┘
```

### 关键交互
- 内置文档标有 🔒 标识，不显示删除按钮
- Monaco Editor 支持 Markdown 语法高亮
- 实时预览用 marked.js（已有库）渲染
- 支持 .md 文件导入和导出
- 新建文档时需选择分类

### 文件变更
- 删除：`frontend/js/pages/knowledge-bases.js`
- 新增：`frontend/js/pages/documents.js`
- 修改：`frontend/index.html`（路由和导航项）
- 修改：`frontend/js/api.js`（新增文档相关 API 方法）

---

## 移除 ChromaDB

- `requirements.txt`：移除 `chromadb`、`sentence-transformers`、`torch`（如仅为 embedding 使用）
- `backend/config.py`：移除 `CHROMA_PERSIST_DIR`、`EMBEDDING_MODEL`
- `backend/app.py`：移除 KB processor 初始化和相关 lifespan 代码
- `.env.example`：移除相关配置项

---

## 数据迁移

旧表数据不迁移，完全删除。迁移脚本：
- 新建 `backend/migrations/replace_knowledge_base_with_documents.py`
- 执行顺序：DROP 旧表 → CREATE 新表 → 种子内置文档

---

## 测试要点

1. 内置文档种子数据：80 篇文档正确写入，is_builtin=True
2. API：CRUD 接口正确，删除内置文档返回 403
3. AI 工具：`list_documents` 和 `read_document` 返回格式正确
4. 前端：分类树、文档列表、Monaco 编辑器、预览均正常
5. 导入/导出：.md 文件往返完整
