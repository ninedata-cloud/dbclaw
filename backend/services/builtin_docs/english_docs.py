"""Maintained English editions of the built-in database runbooks.

These are authored system documents, not runtime translations. Each entry is
seeded as an independent document and linked to its Chinese edition through a
stable translation group.
"""

SCENARIOS = {
    "general-diagnostics": "General diagnostics",
    "performance-diagnostics": "Performance diagnostics",
    "troubleshooting": "Troubleshooting",
    "configuration-sessions": "Configuration and sessions",
    "security-permissions": "Security and permissions",
    "technical-reference": "Technical reference",
}

STANDARD_TOPICS = [
    ("general-diagnostics", "Comprehensive Database Diagnostic Workflow", "Establish impact, timeline, and the constrained resource before changing the system."),
    ("performance-diagnostics", "High CPU Diagnostic and Optimization Workflow", "Separate database CPU demand from host contention and identify the workload responsible for sustained CPU pressure."),
    ("performance-diagnostics", "High Storage Usage Diagnostic and Optimization Workflow", "Measure allocation, growth, reclaimable space, and retention before deleting or shrinking data."),
    ("performance-diagnostics", "High Network Traffic Diagnostic and Optimization Workflow", "Correlate network throughput with sessions, query volume, replication, backups, and client retry behavior."),
    ("performance-diagnostics", "SQL Diagnostic and Optimization Workflow", "Use execution evidence to improve a statement without changing its required result."),
    ("performance-diagnostics", "Slow Write Diagnostic and Optimization Workflow", "Locate latency in locking, logging, storage, checkpoints, replication, or application batching."),
    ("performance-diagnostics", "Index Diagnostic and Optimization Workflow", "Balance read benefit against write cost, memory pressure, storage, and maintenance overhead."),
    ("troubleshooting", "Deadlock Diagnostic and Remediation Workflow", "Capture the deadlock graph, identify the cycle, and correct access order or transaction scope."),
    ("troubleshooting", "Connection Failure Diagnostic Workflow", "Test name resolution, routing, listener state, protocol negotiation, authentication, and authorization in order."),
    ("troubleshooting", "SQL Execution Failure Diagnostic Workflow", "Preserve the exact error and statement context, then distinguish syntax, object, permission, resource, and concurrency failures."),
    ("troubleshooting", "Replication Lag Diagnostic Workflow", "Compare send, receive, replay, and apply positions to locate the stage responsible for lag."),
    ("troubleshooting", "Replication Inconsistency Diagnostic Workflow", "Confirm scope with checksums or row counts and repair only after identifying the divergence mechanism."),
    ("troubleshooting", "Database Startup Failure Diagnostic Workflow", "Follow the first fatal startup error through configuration, storage, recovery, permissions, and port ownership."),
    ("troubleshooting", "Data Loss Recovery Plan", "Protect the remaining evidence, define the recovery point objective, and restore into an isolated target before cutover."),
    ("configuration-sessions", "System Parameter Diagnostic and Optimization Workflow", "Tie every parameter change to a measured symptom, validate its scope, and keep a rollback value."),
    ("configuration-sessions", "Session and Connection Diagnostic Workflow", "Analyze concurrency, idle sessions, transaction age, pooling behavior, blocking, and connection churn."),
    ("security-permissions", "Database Security Assessment", "Review exposure, authentication, encryption, patching, auditing, secrets, and least-privilege controls."),
    ("security-permissions", "User and Privilege Diagnostic Guide", "Trace effective privileges through direct grants and roles, then remove only access proven unnecessary."),
    ("technical-reference", "Transaction Log Technical Reference", "Understand transaction-log generation, retention, archival, recovery, and capacity signals."),
    ("technical-reference", "Database Error Code Reference", "Classify errors by subsystem and use the complete vendor error, state, and context during diagnosis."),
]

CHECKLISTS = {
    "general-diagnostics": ["Confirm user impact and start time", "Collect host and database saturation metrics", "Identify blocking, long-running work, and recent changes", "Form and test one hypothesis at a time"],
    "performance-diagnostics": ["Compare current values with a known-good baseline", "Rank the top workload contributors", "Inspect execution, waits, locks, and resource queues", "Validate improvement under representative load"],
    "troubleshooting": ["Preserve the original error and timestamps", "Check the narrowest failing layer first", "Correlate database, host, network, and application evidence", "Verify recovery and monitor for recurrence"],
    "configuration-sessions": ["Record the current effective value", "Check scope, dependencies, and restart requirements", "Apply one reversible change", "Observe workload and connection behavior after the change"],
    "security-permissions": ["Inventory identities, roles, and trust boundaries", "Review effective rather than declared privileges", "Remove stale access with a rollback plan", "Confirm audit coverage for privileged activity"],
    "technical-reference": ["Use the database-version-specific vendor reference", "Capture complete identifiers and state codes", "Relate the reference to observed runtime evidence", "Avoid changes based on a code alone"],
}


def _content(database: str, title: str, objective: str, scenario_code: str) -> str:
    checklist = "\n".join(f"- {item}" for item in CHECKLISTS[scenario_code])
    return f"""# {database} {title}

## Objective

{objective}

## Safety rules

- Keep user SQL, log lines, identifiers, and vendor errors unchanged in evidence.
- Prefer read-only inspection. Obtain approval before terminating sessions, changing configuration, rebuilding objects, or deleting data.
- Record UTC timestamps, the local time zone, database version, topology, and workload window.
- Define a rollback and a success metric before remediation.

## Diagnostic checklist

{checklist}

## Evidence to collect

1. Database health, wait events, active sessions, blocking relationships, and the most expensive statements.
2. Host CPU, memory, disk latency and capacity, network throughput, and process-level resource use.
3. Relevant configuration, deployment or schema changes, maintenance jobs, and application release events.
4. A before/after sample using the same time window and workload dimensions.

## Decision and remediation

Rank findings by impact and confidence. State which evidence supports each conclusion, then choose the smallest reversible action. Re-run the same measurements after the action and stop if the expected signal does not improve.

## Escalation package

Include the timeline, affected services, topology, exact errors, sanitized evidence, actions already attempted, observed results, and the next decision requiring approval.
"""


def _standard_docs(database: str) -> list[dict]:
    return [
        {
            "category_code": scenario_code,
            "title": f"{database} {title}",
            "content": _content(database, title, objective, scenario_code),
        }
        for scenario_code, title, objective in STANDARD_TOPICS
    ]


OCEANBASE_MYSQL_ENGLISH_DOCS = [
    {
        "category_code": "general-diagnostics",
        "title": "OceanBase MySQL Datasource Onboarding and General Diagnostics",
        "content": _content("OceanBase MySQL", "Datasource Onboarding and General Diagnostics", "Validate tenant connectivity, compatibility mode, monitoring views, and the minimum evidence required for diagnosis.", "general-diagnostics"),
    },
    {
        "category_code": "security-permissions",
        "title": "OceanBase MySQL Monitoring Account Privilege Guide",
        "content": _content("OceanBase MySQL", "Monitoring Account Privilege Guide", "Grant the smallest read-only privilege set needed for tenant metadata and monitoring while keeping operational privileges separate.", "security-permissions"),
    },
    {
        "category_code": "troubleshooting",
        "title": "OceanBase MySQL Compatibility and Graceful-Degradation Guide",
        "content": _content("OceanBase MySQL", "Compatibility and Graceful-Degradation Guide", "Detect unavailable system views or version differences and degrade diagnostics without hiding missing evidence.", "troubleshooting"),
    },
]

ENGLISH_DOCS_MAP = {
    "mysql": _standard_docs("MySQL"),
    "oceanbase-mysql": OCEANBASE_MYSQL_ENGLISH_DOCS,
    "postgresql": _standard_docs("PostgreSQL"),
    "oracle": _standard_docs("Oracle"),
    "sqlserver": _standard_docs("SQL Server"),
}
