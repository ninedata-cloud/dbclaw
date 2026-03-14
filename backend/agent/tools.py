# Tools that can modify state or execute arbitrary commands.
# Users can disable these per-session from the diagnosis UI.
HIGH_RISK_TOOLS = {
    "execute_diagnostic_query": "Execute read-only SQL queries (SELECT, SHOW, EXPLAIN)",
    "execute_os_command": "Execute read-only shell commands on the host via SSH",
    "explain_query": "Run EXPLAIN on SQL queries",
    "execute_any_sql": "⚠️ DANGEROUS: Execute ANY SQL command (INSERT, UPDATE, DELETE, DROP, etc.)",
    "execute_any_os_command": "⚠️ DANGEROUS: Execute ANY OS command (can modify system)",
}


def get_filtered_tools(disabled_tools=None):
    """Return TOOL_DEFINITIONS with disabled tools removed."""
    if not disabled_tools:
        return TOOL_DEFINITIONS
    return [t for t in TOOL_DEFINITIONS if t["function"]["name"] not in disabled_tools]


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
            "name": "search_knowledge_base",
            "description": "Search knowledge bases for relevant documentation. Use when user questions relate to custom configurations, internal procedures, or topics that might be documented in uploaded files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "kb_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional KB IDs to search (if not provided, searches all active KBs in session)"
                    },
                    "top_k": {"type": "integer", "description": "Number of results (default: 5)", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
]
