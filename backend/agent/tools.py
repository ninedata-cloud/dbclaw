from backend.agent.skill_authorization import is_static_tool_authorized


def get_filtered_tools(disabled_tools=None, skill_authorizations=None):
    """Return TOOL_DEFINITIONS after legacy filtering and session authorization checks."""
    filtered = TOOL_DEFINITIONS
    if disabled_tools:
        filtered = [t for t in filtered if t["function"]["name"] not in disabled_tools]
    if skill_authorizations:
        filtered = [
            t for t in filtered
            if is_static_tool_authorized(t.get("function", {}).get("name"), skill_authorizations, disabled_tools)
        ]
    return filtered


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_db_status",
            "description": "Get current database status metrics including connections, throughput, cache hit rates, and key performance indicators.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID"}
                },
                "required": ["connection_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_db_variables",
            "description": "Get database configuration variables/parameters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID"}
                },
                "required": ["connection_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_process_list",
            "description": "Get list of active database processes/sessions to identify blocking or long-running queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID"}
                },
                "required": ["connection_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_slow_queries",
            "description": "Get recent slow queries for performance analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID"}
                },
                "required": ["connection_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_stats",
            "description": "Get table-level statistics including row counts, sizes, and scan patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID"}
                },
                "required": ["connection_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_replication_status",
            "description": "Get database replication/cluster status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID"}
                },
                "required": ["connection_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_db_size",
            "description": "Get database size information including data and index sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID"}
                },
                "required": ["connection_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_diagnostic_query",
            "description": "Execute a read-only SQL query for diagnostic purposes. Only SELECT statements are allowed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID"},
                    "sql": {"type": "string", "description": "The SQL query to execute (SELECT only)"}
                },
                "required": ["connection_id", "sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explain_query",
            "description": "Get the execution plan for a SQL query to analyze its performance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID"},
                    "sql": {"type": "string", "description": "The SQL query to explain"}
                },
                "required": ["connection_id", "sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_os_metrics",
            "description": "Get OS-level metrics (CPU, memory, disk, network, load) from the host server via SSH.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID (must have SSH host configured)"}
                },
                "required": ["connection_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_metric_history",
            "description": "Get historical metric data for trend analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID"},
                    "metric_type": {"type": "string", "description": "Type of metric (db_status, os_metrics)"},
                    "limit": {"type": "integer", "description": "Number of recent snapshots to retrieve", "default": 20}
                },
                "required": ["connection_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_os_command",
            "description": "Execute a shell command on the database host server via SSH. Use this to inspect OS-level details like disk usage (df, du), process info (ps, top), network (netstat, ss), logs (tail, journalctl), kernel params (sysctl), filesystem info, etc. Only read-only diagnostic commands are allowed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_id": {"type": "integer", "description": "The database connection ID (must have SSH host configured)"},
                    "command": {"type": "string", "description": "The shell command to execute, e.g. 'df -h', 'free -m', 'ps aux | head -20'"}
                },
                "required": ["connection_id", "command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_connections",
            "description": "List all configured database connections.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "列出知识库中的诊断文档目录（含摘要）。该工具仅作为知识计划不足时的兜底浏览入口，可按数据库类型过滤。",
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
            "description": "读取指定文档的完整 Markdown 内容。当系统提供的知识计划不足或需要核对原始步骤/命令时再调用。",
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
    },
]
