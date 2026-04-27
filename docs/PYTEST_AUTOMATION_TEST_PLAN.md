# Pytest 自动化测试落地方案

## 1. 目标与验收标准

- 覆盖率目标分阶段推进：`75% -> 80% -> 85%`
- 优先保障关键业务链路可回归，不只追求行覆盖率
- 统一测试分层：`unit / service / api / integration`
- 新增或改动业务代码必须同步补充对应层级测试

## 2. 测试分层与边界

### unit（纯逻辑）

- 覆盖对象：`backend/utils/*`、规则函数、解析器、校验器
- 约束：不访问真实 DB/网络
- 要求：边界值、异常输入、分支条件全覆盖

### service（单服务编排）

- 覆盖对象：`backend/services/*` 中有业务决策逻辑的模块
- 约束：外部依赖（DB/HTTP/IM）允许 mock，服务内部逻辑尽量真实执行
- 要求：成功分支 + 异常分支 + 幂等行为 + 状态更新断言

### api（路由层）

- 覆盖对象：`backend/routers/*`
- 约束：使用 `TestClient`，依赖注入覆盖 `get_db/get_current_user`
- 要求：认证鉴权、参数校验（422）、资源边界（404/403）、错误语义

### integration（跨模块集成）

- 覆盖对象：2~4 个模块联合行为，例如 router -> service -> dispatcher
- 约束：只 mock 外部系统边界（IM webhook、SMTP、第三方 API）
- 要求：至少验证一次完整主流程的输入、状态变化、输出

## 3. 目录与命名规范

- `tests/unit/`：纯单元测试
- `tests/service/`：服务层测试
- `tests/api/`：路由层测试
- `tests/integration/`：集成测试
- 文件命名：`test_<module>_<scenario>.py`
- 每个用例命名包含预期行为：`test_<action>_<expected_result>`

> 现有平铺的 `tests/test_*.py` 可先保持兼容，新增文件按新目录结构落地，逐步迁移旧文件。

## 4. 夹具与测试基础设施

统一在 `tests/conftest.py` 维护基础夹具：

- `admin_user` / `normal_user`
- `fake_async_db`
- `app_factory` / `client_factory`
- `db_override_factory`

建议逐步新增：

- `auth_client_factory`：按用户角色自动注入依赖
- `seed_factory`：集中构造 datasource/alert/integration 等对象
- `frozen_time`：统一控制时间相关逻辑（冷却窗口、去重窗口）

## 5. 高优先级补测清单（P0 -> P2）

### P0（先做）

1. `metric_collector`：
   - 采集成功触发阈值判断
   - 采集失败触发 `system_error` 告警
   - host 指标合并分支
2. `integration_scheduler`：
   - 启用/禁用集成过滤
   - `integration_id` 缺失和数据源不存在
   - 调度异常时不中断批处理
3. `alerts` API：
   - acknowledge/resolve 状态流转
   - 普通用户跨用户订阅访问 403
   - 管理员跨用户查看允许

### P1（第二阶段）

1. `notification_dispatcher`：
   - 渠道路由分发（webhook/mail/dingtalk/feishu/weixin）
   - 渠道失败降级和错误隔离
2. `notification_service`：
   - 模板渲染变量缺失
   - 聚合/去重策略分支
3. `auth/session`：
   - 会话失效
   - 修改密码后会话撤销
   - 登录异常路径

### P2（第三阶段）

1. `app` lifespan 关键组件 smoke 集成测试
2. 多数据库适配层契约测试（接口行为一致性）
3. `/health` 与关键管理接口的全链路回归

## 6. CI 执行策略

- PR 快速检查：
  - `pytest -m "unit or service or api"`
- 主干/夜间全量：
  - `pytest`
- 覆盖率门禁按阶段抬升：
  - 阶段一：`--cov-fail-under=80`
  - 阶段二：`--cov-fail-under=85`

## 7. 建议推进节奏（4 周）

- 第 1 周：完成基建夹具和 P0 的 40%
- 第 2 周：完成 P0，覆盖率稳定到 80%
- 第 3 周：完成 P1，清理脆弱 mock 用例
- 第 4 周：完成 P2，覆盖率冲刺到 85%
