"""
Intent detection for user queries to determine appropriate response style.
"""


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
