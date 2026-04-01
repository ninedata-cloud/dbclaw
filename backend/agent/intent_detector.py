"""
Intent detection for user queries to determine appropriate response style.
"""

import logging

logger = logging.getLogger(__name__)


def detect_query_intent(message: str) -> str:
    """
    Detect user query intent from message content.

    Args:
        message: The user's message text

    Returns:
        One of: 'diagnostic', 'informational', or 'administrative'
    """
    message_lower = message.lower()

    # Diagnostic keywords (Chinese and English)
    diagnostic_keywords = [
        '慢', 'slow', '错误', 'error', '问题', 'problem',
        '故障', 'fault', '诊断', 'diagnose', '优化', 'optimize',
        '为什么', 'why', '怎么办', 'what to do', '解决', 'solve',
        '修复', 'fix', '异常', 'abnormal', '卡', 'stuck',
        '失败', 'fail', '超时', 'timeout', '阻塞', 'block',
        '性能', 'performance', '瓶颈', 'bottleneck', '延迟', 'latency'
    ]

    # Informational keywords (view-only actions)
    informational_keywords = [
        '查看', 'view', '显示', 'show', '列出', 'list',
        '获取', 'get', '什么是', 'what is', '有哪些', 'what are',
        '当前', 'current', '状态', 'status', '信息', 'info',
        '统计', 'stats', '监控', 'monitor', '报告', 'report'
    ]

    # Administrative keywords (action verbs)
    administrative_keywords = [
        '执行', 'execute', '运行', 'run', '创建', 'create',
        '修改', 'modify', '删除', 'delete', '更新', 'update',
        '设置', 'set', '启用', 'enable', '禁用', 'disable',
        '添加', 'add', '移除', 'remove', '配置', 'configure'
    ]

    # Count keyword matches
    diagnostic_score = sum(1 for kw in diagnostic_keywords if kw in message_lower)
    informational_score = sum(1 for kw in informational_keywords if kw in message_lower)
    administrative_score = sum(1 for kw in administrative_keywords if kw in message_lower)

    # Diagnostic takes priority if it has any matches
    if diagnostic_score > 0 and diagnostic_score >= informational_score and diagnostic_score >= administrative_score:
        return 'diagnostic'
    # Administrative takes priority over informational
    elif administrative_score > informational_score:
        return 'administrative'
    else:
        return 'informational'  # Default to informational


async def detect_intent_with_llm(message: str) -> str:
    """
    Use AI to detect intent for ambiguous or short queries.
    Fallback when keyword matching is uncertain.

    Args:
        message: The user's message text

    Returns:
        One of: 'diagnostic', 'informational', or 'administrative'
    """
    from backend.services.ai_agent import get_ai_client

    client = get_ai_client()
    if not client:
        return detect_query_intent(message)

    prompt = f"""你是一个数据库助手意图分类器。根据用户的问题，判断其意图是哪种类型：

- diagnostic（诊断）: 用户遇到问题需要分析根因，如"数据库变慢了"、"连接失败"、"有错误"
- informational（查询）: 用户想查看或了解某些信息，如"查看状态"、"列出慢查询"、"有什么表"
- administrative（操作）: 用户想执行某种操作，如"创建索引"、"删除数据"、"修改配置"

用户问题：{message}

只回答一个词：diagnostic、informational 或 administrative。

回答："""

    try:
        if client.protocol == "anthropic":
            response = await client.client.messages.create(
                model=client.model_name,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}]
            )
            intent = response.content[0].text.strip().lower()
        else:
            response = await client.client.chat.completions.create(
                model=client.model_name,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}]
            )
            intent = response.choices[0].message.content.strip().lower()

        # Validate response
        valid_intents = {'diagnostic', 'informational', 'administrative'}
        if intent in valid_intents:
            logger.debug(f"LLM intent detection: '{message[:30]}...' -> {intent}")
            return intent
        return detect_query_intent(message)
    except Exception as e:
        logger.warning(f"LLM intent detection failed, using keyword fallback: {e}")
        return detect_query_intent(message)
    """
    Detect user query intent from message content.

    Args:
        message: The user's message text

    Returns:
        One of: 'diagnostic', 'informational', or 'administrative'
    """
    message_lower = message.lower()

    # Diagnostic keywords (Chinese and English)
    diagnostic_keywords = [
        '慢', 'slow', '错误', 'error', '问题', 'problem',
        '故障', 'fault', '诊断', 'diagnose', '优化', 'optimize',
        '为什么', 'why', '怎么办', 'what to do', '解决', 'solve',
        '修复', 'fix', '异常', 'abnormal', '卡', 'stuck',
        '失败', 'fail', '超时', 'timeout', '阻塞', 'block',
        '性能', 'performance', '瓶颈', 'bottleneck', '延迟', 'latency'
    ]

    # Informational keywords (view-only actions)
    informational_keywords = [
        '查看', 'view', '显示', 'show', '列出', 'list',
        '获取', 'get', '什么是', 'what is', '有哪些', 'what are',
        '当前', 'current', '状态', 'status', '信息', 'info',
        '统计', 'stats', '监控', 'monitor', '报告', 'report'
    ]

    # Administrative keywords (action verbs)
    administrative_keywords = [
        '执行', 'execute', '运行', 'run', '创建', 'create',
        '修改', 'modify', '删除', 'delete', '更新', 'update',
        '设置', 'set', '启用', 'enable', '禁用', 'disable',
        '添加', 'add', '移除', 'remove', '配置', 'configure'
    ]

    # Count keyword matches
    diagnostic_score = sum(1 for kw in diagnostic_keywords if kw in message_lower)
    informational_score = sum(1 for kw in informational_keywords if kw in message_lower)
    administrative_score = sum(1 for kw in administrative_keywords if kw in message_lower)

    # Diagnostic takes priority if it has any matches
    if diagnostic_score > 0 and diagnostic_score >= informational_score and diagnostic_score >= administrative_score:
        return 'diagnostic'
    # Administrative takes priority over informational
    elif administrative_score > informational_score:
        return 'administrative'
    else:
        return 'informational'  # Default to informational
