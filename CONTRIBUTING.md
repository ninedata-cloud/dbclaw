# 贡献指南

感谢您对 DBClaw 项目的关注！我们欢迎所有形式的贡献，包括但不限于：

- 报告 Bug
- 提交功能建议
- 改进文档
- 提交代码补丁
- 分享使用经验

## 行为准则

参与本项目即表示您同意遵守我们的行为准则：

- 尊重所有贡献者
- 使用友好和包容的语言
- 接受建设性的批评
- 关注对社区最有利的事情
- 对其他社区成员表示同理心

## 如何贡献

### 报告 Bug

如果您发现了 Bug，请在 GitHub Issues 中创建新问题，并包含以下信息：

- **清晰的标题**：简要描述问题
- **环境信息**：
  - DBClaw 版本
  - 操作系统和版本
  - Python 版本
  - 数据库类型和版本
- **重现步骤**：详细的步骤说明
- **预期行为**：您期望发生什么
- **实际行为**：实际发生了什么
- **日志和截图**：相关的错误日志或截图
- **其他信息**：任何可能有帮助的额外信息

### 提交功能建议

我们欢迎新功能建议！请在 GitHub Issues 中创建功能请求，并包含：

- **功能描述**：清晰描述您希望添加的功能
- **使用场景**：为什么需要这个功能？它解决什么问题？
- **建议实现**：如果有想法，请描述可能的实现方式
- **替代方案**：是否考虑过其他解决方案？

### 提交代码

#### 开发环境设置

1. Fork 本仓库到您的 GitHub 账号

2. 克隆您的 Fork
```bash
git clone https://github.com/YOUR_USERNAME/dbclaw.git
cd dbclaw
```

3. 添加上游仓库
```bash
git remote add upstream https://github.com/ninedata/dbclaw.git
```

4. 创建 Python 虚拟环境
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate  # Windows
```

5. 安装依赖
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

6. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，配置数据库连接等
```

7. 启动开发服务器
```bash
python run.py
```

#### 代码规范

**Python 代码**：
- 遵循 PEP 8 代码风格
- 使用有意义的变量和函数名
- 添加必要的注释和文档字符串
- 保持函数简洁，单一职责
- 使用类型注解（Type Hints）

**JavaScript 代码**：
- 使用 ES6+ 语法
- 保持代码简洁易读
- 添加必要的注释
- 避免全局变量污染

**通用规范**：
- 提交前运行测试
- 确保代码没有明显的安全漏洞
- 避免引入不必要的依赖
- 保持向后兼容（除非是破坏性变更）

#### 提交流程

1. **创建功能分支**
```bash
git checkout -b feature/your-feature-name
# 或
git checkout -b fix/your-bug-fix
```

2. **进行修改**
   - 编写代码
   - 添加测试（如果适用）
   - 更新文档

3. **提交更改**
```bash
git add .
git commit -m "feat: 添加新功能描述"
```

提交信息格式：
- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `style:` 代码格式调整（不影响功能）
- `refactor:` 代码重构
- `test:` 测试相关
- `chore:` 构建或辅助工具变动

4. **同步上游更改**
```bash
git fetch upstream
git rebase upstream/main
```

5. **推送到您的 Fork**
```bash
git push origin feature/your-feature-name
```

6. **创建 Pull Request**
   - 访问 GitHub 上您的 Fork
   - 点击 "New Pull Request"
   - 填写 PR 描述：
     - 变更内容
     - 相关 Issue 编号
     - 测试说明
     - 截图（如果是 UI 变更）

#### Pull Request 检查清单

提交 PR 前请确认：

- [ ] 代码遵循项目代码规范
- [ ] 已添加必要的测试
- [ ] 所有测试通过
- [ ] 已更新相关文档
- [ ] 提交信息清晰明确
- [ ] 没有引入安全漏洞
- [ ] 没有破坏现有功能
- [ ] PR 描述完整

### 改进文档

文档改进同样重要！您可以：

- 修正拼写或语法错误
- 改进现有文档的清晰度
- 添加缺失的文档
- 翻译文档到其他语言

文档修改流程与代码提交相同。

## 测试

### 运行测试

```bash
# 运行所有测试
python -m pytest

# 运行特定测试文件
python -m pytest tests/test_skills.py

# 运行特定测试函数
python -m pytest tests/test_skills.py -k test_function_name

# 查看测试覆盖率
python -m pytest --cov=backend tests/

# 按分层运行测试
python -m pytest -m unit
python -m pytest -m service
python -m pytest -m api
```

### 编写测试

- 为新功能添加单元测试
- 为 Bug 修复添加回归测试
- 测试文件放在 `tests/` 目录
- 测试文件命名：`test_*.py`
- 测试函数命名：`test_*`
- 使用 marker 标记测试层级：
  - `@pytest.mark.unit`：纯逻辑单元测试
  - `@pytest.mark.service`：服务层流程测试（依赖 mock）
  - `@pytest.mark.api`：API 路由行为测试

## 代码审查

所有提交都需要经过代码审查。审查者会关注：

- 代码质量和可维护性
- 是否符合项目规范
- 是否有潜在的 Bug 或安全问题
- 测试覆盖率
- 文档完整性

请耐心等待审查，并根据反馈进行修改。

## 发布流程

发布由项目维护者负责：

1. 更新版本号（`backend/version.py`）
2. 更新 `CHANGELOG.md`
3. 创建 Git Tag
4. 构建 Docker 镜像
5. 发布 GitHub Release

## 获取帮助

如果您在贡献过程中遇到问题：

- 查看现有的 Issues 和 Discussions
- 在 GitHub Discussions 中提问
- 发送邮件至：dev@ninedata.com

## 许可证

通过向本项目提交代码，您同意您的贡献将在 MIT 许可证下发布。

## 致谢

感谢所有为 DBClaw 做出贡献的开发者！

您的贡献将被记录在：
- Git 提交历史
- CHANGELOG.md
- GitHub Contributors 页面

---

再次感谢您的贡献！🎉
