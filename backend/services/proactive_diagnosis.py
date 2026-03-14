"""
Proactive Diagnosis Service
主动诊断服务 - 异常检测后自动触发 AI 诊断
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anomaly import Anomaly
from backend.models.diagnostic_case import GuardianAlert
from backend.models.datasource import Datasource
from backend.models.diagnostic_session import DiagnosticSession
from backend.agent.conversation_skills import run_conversation_with_skills

logger = logging.getLogger(__name__)


class ProactiveDiagnosisService:
    """主动诊断服务"""

    def __init__(self):
        self.diagnosis_timeout = 120  # 诊断超时时间（秒）

    async def diagnose_anomaly(
        self,
        db: AsyncSession,
        anomaly_id: int,
        auto_fix: bool = False,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        对异常进行主动诊断

        Args:
            db: 数据库会话
            anomaly_id: 异常记录 ID
            auto_fix: 是否启用自动修复
            force: 是否强制诊断（跳过智能判断）

        Returns:
            诊断结果字典
        """
        try:
            # 1. 获取异常记录
            result = await db.execute(
                select(Anomaly).where(Anomaly.id == anomaly_id)
            )
            anomaly = result.scalar_one_or_none()

            if not anomaly:
                logger.error(f"Anomaly {anomaly_id} not found")
                return {"success": False, "error": "Anomaly not found"}

            # 2. 获取数据��信息
            result = await db.execute(
                select(Datasource).where(Datasource.id == anomaly.datasource_id)
            )
            datasource = result.scalar_one_or_none()

            if not datasource:
                logger.error(f"Datasource {anomaly.datasource_id} not found")
                return {"success": False, "error": "Datasource not found"}

            # 3. 检查是否需要诊断（如果不是强制诊断）
            if not force and anomaly.diagnosis_count > 0:
                should_diagnose, decision_reason = await self._should_diagnose(db, anomaly, datasource)
                if not should_diagnose:
                    # 记录跳过决策
                    anomaly.diagnosis_decision = 'skipped'
                    anomaly.diagnosis_decision_reason = decision_reason
                    anomaly.diagnosis_decision_at = datetime.utcnow()
                    await db.commit()

                    logger.info(f"⏭️ Skipping diagnosis for anomaly {anomaly_id} - {decision_reason}")
                    return {
                        "success": True,
                        "skipped": True,
                        "reason": decision_reason,
                        "anomaly_id": anomaly_id
                    }

            # 4. 记录诊断决策
            anomaly.diagnosis_decision = 'diagnosed'
            anomaly.diagnosis_decision_reason = decision_reason if not force else 'Force diagnosis (manual trigger)'
            anomaly.diagnosis_decision_at = datetime.utcnow()

            # 5. 更新异常状态为诊断中
            anomaly.status = 'diagnosing'
            await db.commit()

            logger.info(f"🔍 Starting proactive diagnosis for anomaly {anomaly_id} (attempt #{anomaly.diagnosis_count + 1})")

            # 5. 构建诊断提示
            diagnosis_prompt = self._build_diagnosis_prompt(anomaly, datasource)

            # 6. 调用 AI 进行诊断
            messages = [{"role": "user", "content": diagnosis_prompt}]

            ai_response_parts = []
            tool_results = []

            async for event in run_conversation_with_skills(
                messages=messages,
                datasource_id=datasource.id,
                model_id=None,  # 使用默认模型
                kb_ids=None,
                db=db,
                user_id=None,
                session_id=None
            ):
                if event["type"] == "content":
                    ai_response_parts.append(event["content"])
                elif event["type"] == "tool_result":
                    tool_results.append({
                        "tool": event.get("tool_name"),
                        "result": event.get("result")
                    })
                elif event["type"] == "error":
                    logger.error(f"AI diagnosis error: {event.get('message')}")
                    anomaly.status = 'detected'
                    await db.commit()
                    return {"success": False, "error": event.get("message")}
                elif event["type"] == "done":
                    break

            full_diagnosis = "".join(ai_response_parts)

            # 7. 解析 AI 响应，提取根因和建议
            parsed_result = self._parse_ai_diagnosis(full_diagnosis)

            # 8. 更新异常记录
            anomaly.ai_diagnosis = full_diagnosis
            anomaly.root_cause = parsed_result.get("root_cause", "")
            anomaly.recommended_actions = json.dumps(parsed_result.get("recommended_actions", []))
            anomaly.status = 'detected'  # 诊断完成，等待处理
            anomaly.diagnosis_count = (anomaly.diagnosis_count or 0) + 1

            # 保存当前数据快照用于下次比较
            anomaly.last_diagnosis_snapshot = anomaly.context_snapshot

            try:
                await db.commit()
                await db.refresh(anomaly)
            except Exception as e:
                await db.rollback()
                logger.error(f"Error committing diagnosis results for anomaly {anomaly_id}: {e}")
                raise

            logger.info(f"✅ Proactive diagnosis completed for anomaly {anomaly_id}")

            # 9. 创建告警
            alert = await self._create_alert(db, anomaly, datasource, parsed_result)

            # 10. 如果启用自动修复且风险可控，执行修复
            if auto_fix and parsed_result.get("auto_fixable", False):
                await self._attempt_auto_fix(db, anomaly, parsed_result)

            return {
                "success": True,
                "anomaly_id": anomaly_id,
                "diagnosis": full_diagnosis,
                "root_cause": parsed_result.get("root_cause"),
                "recommended_actions": parsed_result.get("recommended_actions"),
                "alert_id": alert.id if alert else None
            }

        except Exception as e:
            logger.error(f"Error in proactive diagnosis for anomaly {anomaly_id}: {e}", exc_info=True)

            # 恢复异常状态
            try:
                result = await db.execute(
                    select(Anomaly).where(Anomaly.id == anomaly_id)
                )
                anomaly = result.scalar_one_or_none()
                if anomaly and anomaly.status == 'diagnosing':
                    anomaly.status = 'detected'
                    await db.commit()
            except:
                pass

            return {"success": False, "error": str(e)}

    async def _should_diagnose(
        self,
        db: AsyncSession,
        anomaly: Anomaly,
        datasource: Datasource
    ) -> tuple[bool, str]:
        """
        智能判断是否需要再次诊断（基于规则 + AI）

        Args:
            db: 数据库会话
            anomaly: 异常记录
            datasource: 数据源

        Returns:
            (是否需要诊断, 决策原因)
        """
        try:
            # 规则1: 首次检测到的异常，必须诊断
            if not anomaly.last_diagnosis_snapshot or anomaly.diagnosis_count == 0:
                reason = "First-time anomaly detection"
                logger.info(f"✅ First-time anomaly {anomaly.id}, will diagnose")
                return True, reason

            # 规则2: CRITICAL 级别异常，如果距离上次诊断超过30分钟，重新诊断
            if anomaly.severity == 'CRITICAL':
                time_since_detection = datetime.utcnow() - anomaly.detected_at
                if time_since_detection > timedelta(minutes=30):
                    reason = f"Critical anomaly aged {int(time_since_detection.total_seconds() / 60)} minutes"
                    logger.info(f"✅ Critical anomaly {anomaly.id} aged >30min, will diagnose")
                    return True, reason

            # 规则3: 检查是否有近期相似异常已经诊断过
            similar_diagnosed = await self._check_similar_diagnosed_anomaly(db, anomaly, datasource)
            if similar_diagnosed:
                reason = "Similar anomaly diagnosed within 30 minutes"
                logger.info(f"⏭️ Similar anomaly recently diagnosed for {anomaly.id}, skipping")
                return False, reason

            # 规则4: 解析上次和当前的数据快照，进行快速规则判断
            try:
                last_snapshot = json.loads(anomaly.last_diagnosis_snapshot) if isinstance(anomaly.last_diagnosis_snapshot, str) else anomaly.last_diagnosis_snapshot
                current_snapshot = json.loads(anomaly.context_snapshot) if isinstance(anomaly.context_snapshot, str) else anomaly.context_snapshot
            except:
                reason = "Failed to parse snapshots, will diagnose for safety"
                logger.warning(f"Failed to parse snapshots for anomaly {anomaly.id}, will diagnose")
                return True, reason

            # 规则5: 快速检查关键指标变化
            significant_change, changed_metrics = self._check_significant_metric_change(last_snapshot, current_snapshot)
            if not significant_change:
                reason = "No significant metric change detected (threshold: 20%)"
                logger.info(f"⏭️ No significant metric change for anomaly {anomaly.id}, skipping")
                return False, reason

            # 规则6: 如果通过了所有快速规则，但仍不确定，使用 AI 判断（仅在必要时）
            # 限制：只有在诊断次数 < 3 且有显著变化时才使用 AI
            if anomaly.diagnosis_count < 3 and significant_change:
                logger.info(f"🤖 Using AI to decide diagnosis for anomaly {anomaly.id}")
                should_diagnose, ai_reason = await self._ai_should_diagnose(db, anomaly, datasource, last_snapshot, current_snapshot)
                reason = f"AI decision: {ai_reason} (changed metrics: {', '.join(changed_metrics)})"
                return should_diagnose, reason

            # 默认：如果诊断次数过多，跳过
            reason = f"Already diagnosed {anomaly.diagnosis_count} times, exceeds limit"
            logger.info(f"⏭️ Anomaly {anomaly.id} diagnosed {anomaly.diagnosis_count} times, skipping")
            return False, reason

        except Exception as e:
            reason = f"Error in decision logic: {str(e)}"
            logger.error(f"Error in _should_diagnose for anomaly {anomaly.id}: {e}")
            return False, reason  # 出错时默认不诊断，避免过度触发

    async def _check_similar_diagnosed_anomaly(
        self,
        db: AsyncSession,
        anomaly: Anomaly,
        datasource: Datasource
    ) -> bool:
        """
        检查是否有近期相似的异常已经诊断过

        Args:
            db: 数据库会话
            anomaly: 当前异常
            datasource: 数据源

        Returns:
            是否存在相似的已诊断异常
        """
        try:
            # 查找最近30分钟内相同类型、相同指标的异常
            cutoff_time = datetime.utcnow() - timedelta(minutes=30)

            result = await db.execute(
                select(Anomaly).where(
                    and_(
                        Anomaly.datasource_id == datasource.id,
                        Anomaly.anomaly_type == anomaly.anomaly_type,
                        Anomaly.affected_metrics == anomaly.affected_metrics,
                        Anomaly.detected_at >= cutoff_time,
                        Anomaly.id != anomaly.id,  # 排除当前异常
                        Anomaly.diagnosis_count > 0  # 已经诊断过
                    )
                ).order_by(desc(Anomaly.detected_at)).limit(1)
            )

            similar = result.scalar_one_or_none()
            return similar is not None

        except Exception as e:
            logger.error(f"Error checking similar anomalies: {e}")
            return False

    def _check_significant_metric_change(
        self,
        last_snapshot: Dict[str, Any],
        current_snapshot: Dict[str, Any],
        threshold: float = 0.20  # 20% 变化阈值
    ) -> tuple[bool, List[str]]:
        """
        检查关键指标是否有显著变化

        Args:
            last_snapshot: 上次快照
            current_snapshot: 当前快照
            threshold: 变化阈值（默认20%）

        Returns:
            (是否有显著变化, 变化的指标列表)
        """
        # 关键指标列表
        key_metrics = [
            'connections', 'qps', 'tps', 'cpu_usage', 'memory_usage',
            'disk_usage', 'load_avg_1min', 'cache_hit_rate', 'slow_queries',
            'threads_running', 'innodb_row_lock_waits', 'deadlocks'
        ]

        changed_metrics = []

        for metric in key_metrics:
            last_value = last_snapshot.get(metric)
            current_value = current_snapshot.get(metric)

            # 跳过缺失的指标
            if last_value is None or current_value is None:
                continue

            # 转换为数值
            try:
                last_val = float(last_value)
                current_val = float(current_value)
            except (ValueError, TypeError):
                continue

            # 避免除零
            if last_val == 0:
                if current_val > 0:
                    changed_metrics.append(f"{metric}(0→{current_val:.1f})")
                    logger.info(f"📊 Significant change detected in {metric}: 0 -> {current_val}")
                continue

            # 计算变化百分比
            change_percent = abs((current_val - last_val) / last_val)

            if change_percent > threshold:
                changed_metrics.append(f"{metric}({change_percent*100:.1f}%)")
                logger.info(f"📊 Significant change detected in {metric}: {last_val} -> {current_val} ({change_percent*100:.1f}%)")

        return len(changed_metrics) > 0, changed_metrics

    async def _ai_should_diagnose(
        self,
        db: AsyncSession,
        anomaly: Anomaly,
        datasource: Datasource,
        last_snapshot: Dict[str, Any],
        current_snapshot: Dict[str, Any]
    ) -> tuple[bool, str]:
        """
        使用 AI 判断是否需要诊断（仅在必要时调用）

        Args:
            db: 数据库会话
            anomaly: 异常记录
            datasource: 数据源
            last_snapshot: 上次快照
            current_snapshot: 当前快照

        Returns:
            (是否需要诊断, AI判断原因)
        """
        try:
            # 构建简化的 AI 判断提示
            prompt = f"""判断是否需要对数据库异常进行再次诊断。

数据库: {datasource.name} ({datasource.db_type.upper()})
异常类型: {anomaly.anomaly_type}
严重程度: {anomaly.severity}
已诊断: {anomaly.diagnosis_count} 次

关键指标对比:
"""
            # 只包含变化的指标
            key_metrics = ['connections', 'qps', 'cpu_usage', 'memory_usage', 'cache_hit_rate']
            for metric in key_metrics:
                last_val = last_snapshot.get(metric)
                curr_val = current_snapshot.get(metric)
                if last_val is not None and curr_val is not None:
                    prompt += f"- {metric}: {last_val} -> {curr_val}\n"

            prompt += f"""
上次诊断结论: {anomaly.ai_diagnosis[:200] if anomaly.ai_diagnosis else 'N/A'}...

请判断是否需要再次诊断。只在以下情况回答 YES:
1. 关键指标变化超过30%
2. 出现新的异常模式
3. 严重程度明显升级

请只回答 "YES" 或 "NO"（一个词）。
"""

            # 调用 AI（使用轻量级模型）
            messages = [{"role": "user", "content": prompt}]
            ai_response_parts = []

            async for event in run_conversation_with_skills(
                messages=messages,
                datasource_id=datasource.id,
                model_id=None,
                kb_ids=None,
                db=db,
                user_id=None,
                session_id=None
            ):
                if event["type"] == "content":
                    ai_response_parts.append(event["content"])
                elif event["type"] == "done":
                    break
                elif event["type"] == "error":
                    logger.error(f"AI judgment error: {event.get('message')}")
                    return False  # AI 出错时默认不诊断

            response = "".join(ai_response_parts).strip().upper()
            should_diagnose = "YES" in response[:10]  # 只检查前10个字符

            # 提取AI的判断原因（取前100个字符）
            ai_reason = response[:100] if response else "No response from AI"

            logger.info(f"🤖 AI decision for anomaly {anomaly.id}: {response[:50]}")
            return should_diagnose, ai_reason

        except Exception as e:
            logger.error(f"Error in AI diagnosis decision: {e}")
            return False, f"AI error: {str(e)}"  # 出错时默认不诊断

    def _build_diagnosis_prompt(self, anomaly: Anomaly, datasource: Datasource) -> str:
        """构建诊断提示"""

        # 解析受影响的指标
        try:
            affected_metrics = json.loads(anomaly.affected_metrics) if isinstance(anomaly.affected_metrics, str) else anomaly.affected_metrics
            metric_name = affected_metrics[0] if affected_metrics else "unknown"
        except:
            metric_name = "unknown"

        # 解析上下文快照
        try:
            context = json.loads(anomaly.context_snapshot) if isinstance(anomaly.context_snapshot, str) else anomaly.context_snapshot
        except:
            context = {}

        prompt = f"""🚨 异常检测告警 - 需要立即诊断

数据库: {datasource.name} ({datasource.db_type.upper()})
检测时间: {anomaly.detected_at.strftime('%Y-%m-%d %H:%M:%S') if anomaly.detected_at else 'N/A'}

异常详情:
- 异常类型: {anomaly.anomaly_type}
- 严重程度: {anomaly.severity}
- 受影响指标: {metric_name}
- 基线值: {anomaly.baseline_value:.2f}
- 当前值: {anomaly.current_value:.2f}
- 偏差: {anomaly.deviation_percent:.2f}%

系统上下文:
"""

        # 添加关键上下文信息
        key_metrics = ['connections', 'qps', 'tps', 'cpu_usage', 'memory_usage', 'disk_usage',
                      'load_avg_1min', 'cache_hit_rate']

        for key in key_metrics:
            if key in context and context[key] is not None:
                prompt += f"- {key}: {context[key]}\n"

        prompt += f"""

请执行以下任务:
1. 调用相关诊断技能收集更多信息（如慢查询、连接列表、表统计等）
2. 分析异常的根本原因
3. 评估影响范围和严重程度
4. 提供具体的解决建议（按优先级排序）
5. 如果可以安全地自动修复，请说明具体步骤

请以结构化的方式回复:
## 根本原因
[详细分析]

## 影响评估
[影响范围和严重程度]

## 解决建议
1. [建议1 - 优先级: 高/中/低]
2. [建议2]
...

## 自动修复可行性
[是否可以自动修复，风险评估]
"""

        return prompt

    def _parse_ai_diagnosis(self, diagnosis: str) -> Dict[str, Any]:
        """解析 AI 诊断结果"""

        result = {
            "root_cause": "",
            "recommended_actions": [],
            "auto_fixable": False
        }

        # 简单的文本解析（可以后续优化为更智能的解析）
        lines = diagnosis.split('\n')

        current_section = None
        root_cause_lines = []
        action_lines = []

        for line in lines:
            line = line.strip()

            if '## 根本原因' in line or '## Root Cause' in line:
                current_section = 'root_cause'
                continue
            elif '## 解决建议' in line or '## 推荐操作' in line or '## Recommended Actions' in line or '## 解决方案' in line:
                current_section = 'actions'
                continue
            elif '## 自动修复' in line or '## Auto Fix' in line:
                current_section = 'auto_fix'
                continue
            elif line.startswith('##'):
                current_section = None
                continue

            if current_section == 'root_cause' and line:
                root_cause_lines.append(line)
            elif current_section == 'actions' and line:
                # 提取建议（通常以数字或 - 开头）
                if line[0].isdigit() or line.startswith('-') or line.startswith('•'):
                    action_lines.append(line.lstrip('0123456789.-•').strip())
            elif current_section == 'auto_fix' and line:
                # 检查是否提到可以自动修复
                if any(keyword in line.lower() for keyword in ['可以', 'yes', 'safe', '安全', 'feasible']):
                    result["auto_fixable"] = True

        result["root_cause"] = ' '.join(root_cause_lines) if root_cause_lines else diagnosis[:500]
        result["recommended_actions"] = action_lines if action_lines else ["请查看完整诊断报告"]

        return result

    async def _create_alert(
        self,
        db: AsyncSession,
        anomaly: Anomaly,
        datasource: Datasource,
        diagnosis_result: Dict[str, Any]
    ) -> Optional[GuardianAlert]:
        """创建告警"""

        try:
            # 解析受影响的指标
            try:
                affected_metrics = json.loads(anomaly.affected_metrics) if isinstance(anomaly.affected_metrics, str) else anomaly.affected_metrics
                metric_name = affected_metrics[0] if affected_metrics else "unknown"
            except:
                metric_name = "unknown"

            # 构建告警标题和消息
            title = f"{datasource.name} - {metric_name} 异常"

            message = f"""检测到 {anomaly.severity} 级别异常:
- 指标: {metric_name}
- 当前值: {anomaly.current_value:.2f}
- 基线值: {anomaly.baseline_value:.2f}
- 偏差: {anomaly.deviation_percent:.2f}%

根本原因: {diagnosis_result.get('root_cause', 'N/A')[:200]}

建议操作:
"""

            for i, action in enumerate(diagnosis_result.get('recommended_actions', [])[:3], 1):
                message += f"{i}. {action}\n"

            # 创建告警
            alert = GuardianAlert(
                datasource_id=datasource.id,
                anomaly_id=anomaly.id,
                severity=anomaly.severity,
                title=title,
                message=message,
                channels=json.dumps(['chat', 'push']),  # 默认通过聊天和推送通知
                status='pending'
            )

            db.add(alert)
            await db.commit()
            await db.refresh(alert)

            logger.info(f"📢 Alert created: {alert.id} for anomaly {anomaly.id}")

            return alert

        except Exception as e:
            logger.error(f"Error creating alert: {e}")
            return None

    async def _attempt_auto_fix(
        self,
        db: AsyncSession,
        anomaly: Anomaly,
        diagnosis_result: Dict[str, Any]
    ):
        """尝试自动修复"""

        try:
            logger.info(f"🔧 Attempting auto-fix for anomaly {anomaly.id}")

            # TODO: 实现自动修复逻辑
            # 1. 评估风险
            # 2. 执行修复操作
            # 3. 验证修复结果
            # 4. 记录修复动作

            # 目前只记录日志，实际修复需要根据具体场景实现
            logger.info(f"Auto-fix not yet implemented for anomaly {anomaly.id}")

        except Exception as e:
            logger.error(f"Error in auto-fix for anomaly {anomaly.id}: {e}")
