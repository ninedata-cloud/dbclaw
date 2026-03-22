# AGPL License & README Documentation Design

**Date:** 2026-03-22
**Status:** Approved

---

## 目标 / Goal

为 DBGuard 开源项目添加 AGPL-3.0 许可证文件和双语 README，使项目符合开源发布标准，帮助用户快速了解和上手。

## 文件清单 / Files

1. `LICENSE` — AGPL-3.0 标准全文
2. `README.md` — 双语（中/英）项目介绍文档

## LICENSE 设计

- 使用 GNU Affero General Public License v3.0 标准全文
- 版权年份：2026
- 版权持有人：DBGuard Authors（占位符）

## README.md 设计

### 结构（功能导向型）

```
# DBGuard
[Badge栏] License | Python版本

## 简介 / Overview
中英各一段，4-5句

## ✨ 核心特性 / Features
6项核心能力，图标列表，双语

## 🖥 架构图 / Architecture
占位符（截图待补充）

## 🚀 快速开始 / Quick Start
- 环境要求
- 安装步骤
- 启动命令
- 默认账号

## ⚙️ 配置 / Configuration
.env 关键变量表格

## 📚 文档 / Documentation
指向 docs/ 的链接

## 📄 许可证 / License
AGPL-3.0 说明 + 商业使用提示
```

### 语言策略
- 标题和章节标题：双语（中/英并列）
- 正文内容：先中文后英文
- 代码和命令：只写一次（语言无关）

### 许可证章节要点
- 说明 AGPL-3.0 允许：自由使用、修改、分发，但衍生作品须同等开源
- 明确商业使用提示：若需闭源部署或 SaaS 化，需联系获取商业授权
- GitHub 仓库地址暂用占位符 `https://github.com/your-org/dbguard`

## 不在本次范围内 / Out of Scope

- `CONTRIBUTING.md`（贡献指南）
- `COMMERCIAL_LICENSE.md`（商业许可协议正文）
- CI/CD 配置、Issue 模板等
