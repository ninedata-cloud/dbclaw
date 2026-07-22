(function (global) {
    global.DBClawLocales = global.DBClawLocales || {};
    global.DBClawLocales['en-US'] = {
        app: {
            title: 'DBClaw Database Intelligence Guardian',
            subtitle: ''
        },
        common: {
            language: 'Language', chinese: '简体中文', english: 'English',
            confirm: 'Confirm', cancel: 'Cancel', save: 'Save', create: 'Create', edit: 'Edit',
            delete: 'Delete', close: 'Close', retry: 'Retry', search: 'Search', loading: 'Loading...',
            actions: 'Actions', status: 'Status', enabled: 'Enabled', disabled: 'Disabled',
            yes: 'Yes', no: 'No', all: 'All', none: 'None', unknown: 'Unknown',
            success: 'Operation completed', failed: 'Operation failed', requestFailed: 'Request failed', noData: 'No data'
        },
        auth: {
            username: 'Username', password: 'Password', usernamePlaceholder: 'Enter your username',
            passwordPlaceholder: 'Enter your password', signIn: 'Sign in', signingIn: 'Signing in...',
            required: 'Enter your username and password', failed: 'Sign-in failed',
            sessionExpired: 'Your session has expired. Please sign in again'
        },
        language: {
            switch: 'Switch language',
            unsavedConfirm: 'Switching languages will reload this page and discard unsaved changes. Continue?',
            saveFailed: 'Could not save the language preference: {message}'
        },
        datePicker: {
            open: 'Open date picker', previousMonth: 'Previous month', nextMonth: 'Next month',
            today: 'Today', clear: 'Clear', cancel: 'Cancel', apply: 'Apply',
            hour: 'Hour', minute: 'Minute', selectDate: 'Select date', selectDateTime: 'Select date and time'
        },
        placeholders: {
            selectDatasource: 'Select a datasource', searchSkills: 'Search names, tags, and descriptions...',
            skillId: 'e.g. my_custom_skill', skillName: 'e.g. My Custom Skill', version: 'e.g. 1.0.0',
            categories: 'e.g. diagnostics, monitoring', searchDatasource: 'Search by name, IP, host, or database...',
            filterTags: 'Filter tags (comma-separated; combinations supported)', silenceReason: 'e.g. planned maintenance or a known issue being handled',
            searchParams: 'Search parameters...', configCategories: 'e.g. external_api, system', keepOriginal: 'Leave blank to keep the current value',
            searchHost: 'Search by name or IP...', hostName: 'Production server', keepUnchanged: '(keep unchanged)',
            username: 'Username', passwordMin: 'Password (at least 6 characters)', displayNameOptional: 'Display name (optional)',
            emailOptional: 'Email (optional)', phoneOptional: 'Phone (optional)', newPasswordMin: 'New password (at least 6 characters)',
            symptomTags: 'connection failure, high CPU', documentTitle: 'Enter a document title',
            chatQuestion: 'Ask a database question. Press Ctrl/Command+Enter to send...',
            alertTemplateName: 'e.g. Standard Production Alerts', alertTemplateDescription: 'Describe the applicable instances or scenarios',
            customExpression: 'e.g. cpu_usage > 80 and connections_active > 120',
            aiPolicy: 'e.g. Trigger a high-priority alert when CPU, disk, and connection anomalies persist and worsen.',
            threshold: 'Threshold {unit}', durationSeconds: 'Duration (seconds)', searchAlerts: 'Search titles or content',
            contextWindow: 'e.g. 200000', keepApiKey: 'Leave blank to keep the current key',
            modelTestMessage: 'e.g. Introduce yourself in one sentence', startDate: 'Start date', endDate: 'End date',
            searchTasks: 'Search tasks...', configuredKeep: 'Already configured; leave blank to keep it unchanged',
            searchInstances: 'Search names, hosts, databases, or tags', searchInstanceConfig: 'Search parameter names, values, or categories',
            searchSessions: 'Search SQL or clients', filterUser: 'Filter by user', instanceSilenceReason: 'e.g. planned maintenance',
            searchSql: 'Search by SQL ID or SQL text...'
        },
        integrations: {
            title: 'Integration Management', loadBuiltins: 'Load Built-in Templates', create: 'Create Integration',
            emptyTitle: 'No integrations', emptyHint: 'Load a built-in template or create an integration to get started',
            name: 'Name *', type: 'Type *', description: 'Description', category: 'Category *', select: 'Select',
            enable: 'Enable this integration', schema: 'Configuration Schema (JSON)', schemaHint: 'Defines test and runtime parameters.',
            code: 'Code *', codeHint: 'Maintain the complete implementation here for easier review and editing.',
            typeOutbound: 'Outbound Notification', typeInbound: 'Inbound Metrics', typeBot: 'Bot', uncategorized: 'Uncategorized',
            typeOutboundDesc: 'Send alerts, recoveries, and execution results to external systems', typeInboundDesc: 'Collect metrics from external platforms for monitoring',
            typeBotDesc: 'Receive messages through IM bots and trigger automation', customCapability: 'Custom integration capability',
            categoryEmail: 'Email', categorySms: 'SMS', categoryIm: 'Instant Messaging', categoryMonitoring: 'Monitoring',
            categoryMonitoringSystem: 'Monitoring System', categoryCustom: 'Custom', categoryOther: 'Other',
            weixinBot: 'Weixin Bot', enterpriseWechatBot: 'WeCom Bot', feishuBot: 'Feishu Bot', dingtalkBot: 'DingTalk Bot',
            statusNotReady: 'Not Configured', statusPending: 'Awaiting Scan', statusConfigured: 'Configured', statusRunning: 'Running',
            statusFailed: 'Failed', statusEnabled: 'Enabled', statusDisabled: 'Disabled', statusLoggedIn: 'Signed In',
            statusLoginFailed: 'Sign-in Failed', bindingStatus: '{name} Binding Status', configureBot: 'Configure Bot', builtin: 'Built-in',
            viewDetails: 'View Details', test: 'Test', edit: 'Edit', delete: 'Delete', close: 'Close', cancel: 'Cancel', save: 'Save',
            detailStatus: 'Status', detailType: 'Type', detailCategory: 'Category', detailDescription: 'Description', detailSchema: 'Configuration Schema', detailCode: 'Code',
            testDatasource: 'Test Datasource', loadDatasourceFailed: 'Failed to load datasources: {message}', testTitle: 'Test {name}',
            noTestParams: 'This integration needs no additional parameters and can be tested directly.', testResult: 'Test Result', runTest: 'Run Test',
            loadFailed: 'Failed to load integrations: {message}', testSucceeded: 'Test succeeded', testFailed: 'Test failed: {message}',
            deleteConfirm: 'Are you sure you want to delete this integration?', deleted: 'Integration deleted', deleteFailed: 'Delete failed: {message}',
            editTitle: 'Edit Integration', required: 'Complete all required fields', invalidSchema: 'Invalid configuration schema: {message}',
            updated: 'Integration updated', updateFailed: 'Update failed: {message}', builtinsLoaded: 'Built-in templates loaded',
            builtinLoadFailed: 'Load failed: {message}', createTitle: 'Create Integration', created: 'Integration created', createFailed: 'Create failed: {message}',
            noDescription: 'No description',
            builtinNames: {
                feishuWebhook: 'Feishu Webhook Notification', dingtalkWebhook: 'DingTalk Webhook Notification', email: 'Email Notification',
                genericWebhook: 'Generic Webhook Notification', aliyunRds: 'Alibaba Cloud RDS Metrics',
                huaweiRds: 'Huawei Cloud RDS Metrics', tencentRds: 'Tencent Cloud RDS Metrics',
                feishuBot: 'Feishu Bot Conversation', dingtalkBot: 'DingTalk Bot Conversation', weixinBot: 'Weixin Bot Conversation',
                enterpriseWechatBot: 'WeCom Bot Conversation', enterpriseWechatWebhook: 'WeCom Webhook Notification'
            },
            builtinDescriptions: {
                feishuWebhook: 'Send interactive card notifications through a Feishu webhook', dingtalkWebhook: 'Send Markdown messages through a DingTalk webhook',
                email: 'Send HTML email through SMTP', genericWebhook: 'Send JSON HTTP requests to any webhook endpoint',
                aliyunRds: 'Collect MySQL, PostgreSQL, and SQL Server metrics through the Alibaba Cloud RDS API; AccessKey values come from system settings',
                huaweiRds: 'Collect RDS metrics through the Huawei Cloud CES API; AK/SK values come from system parameters',
                tencentRds: 'Collect MySQL, PostgreSQL, SQL Server, and TDSQL-C MySQL metrics from Tencent Cloud Monitor; SecretId/SecretKey come from system parameters',
                feishuBot: 'Inbound Feishu bot conversations for database diagnosis sessions',
                dingtalkBot: 'Inbound DingTalk bot conversations using a Stream Mode long connection',
                weixinBot: 'Inbound Weixin bot conversations over the OpenClaw protocol using long polling',
                enterpriseWechatBot: 'Inbound WeCom bot conversations for database diagnosis sessions',
                enterpriseWechatWebhook: 'Send alert and event notifications through a WeCom webhook'
            },
            hints: {
                aliyun: 'Currently supports Alibaba Cloud RDS for MySQL, PostgreSQL, and SQL Server. Before testing, configure <code>external_instance_id</code> on the datasource and ensure its database type matches the Alibaba Cloud instance engine.',
                huawei: 'Before testing, configure <code>external_instance_id</code> on the datasource. <code>region_id</code> locates Huawei Cloud CES/IAM endpoints and cannot be inferred from the instance ID alone. <code>AK/SK</code> values are read from system parameters and are not entered during testing.',
                tencent: 'Before testing, configure <code>external_instance_id</code> and match it to the database type. MySQL/TDSQL-C use an instance ID; PostgreSQL/SQL Server usually use the monitoring <code>resourceId</code>. Use a standard <code>region_id</code> such as <code>ap-guangzhou</code>; documented aliases such as <code>gz</code> or <code>1</code> are also supported. <code>SecretId</code> and <code>SecretKey</code> are read from system parameters.'
            },
            notes: {
                feishu: 'Feishu uses long-connection mode by default. Set <code>APP_ID</code> and <code>APP_SECRET</code> at the top of the code. <code>SIGNING_SECRET</code> is only needed when retaining public event callbacks.',
                dingtalk: 'DingTalk uses a Stream Mode long connection by default. Configure <code>dingtalk_client_id</code> and <code>dingtalk_client_secret</code> in system parameters. The bot connects automatically after the backend restarts.',
                generic: 'Paste a complete Python template in the code area. Inbound metrics implement <code>fetch_metrics</code>; outbound notifications implement <code>send_notification</code>.'
            },
            schemaFields: {
                secretOptional: 'Signing Secret (optional)', secret: 'Signing Secret', recipient: 'Recipient', ccOptional: 'CC (optional)',
                httpMethod: 'HTTP Method', authMethod: 'Authentication Method', authTokenOptional: 'Authentication Token (optional)', regionId: 'Region ID',
                areaId: 'Region ID', projectIdOptional: 'Project ID (optional)', region: 'Region', mysqlInstanceType: 'MySQL Instance Type (optional)',
                feishuWebhook: 'Feishu bot webhook URL', feishuSecret: 'Feishu bot signing secret used to verify requests',
                dingtalkWebhook: 'DingTalk bot webhook URL', dingtalkSecret: 'DingTalk bot signing secret',
                recipientHelp: 'Recipient email addresses, separated by commas', ccHelp: 'CC email addresses, separated by commas',
                targetWebhook: 'Target webhook URL', aliyunRegion: 'Alibaba Cloud region ID, such as cn-hangzhou',
                huaweiRegion: 'Huawei Cloud region ID, such as cn-north-4 or cn-east-3. CES/IAM endpoints depend on region_id.',
                projectHelp: 'Leave blank to locate the project ID automatically from region_id',
                tencentRegion: 'Tencent Cloud region, such as ap-guangzhou or ap-shanghai. SQL Server metrics and request headers depend on it.',
                mysqlInstanceHelp: 'MySQL only. The default 1 means primary instance; use 3 for read replicas or proxy for proxy nodes.'
            },
            weixin: {
                loadFailed: 'Failed to load Weixin bot status: {message}', title: 'Weixin Bot Configuration', loginStatus: 'Sign-in Status',
                polling: 'The backend polling service is receiving messages automatically', error: 'Error: {message}', logout: 'Sign Out',
                step1: 'Step 1. Get a Sign-in QR Code', qrHelp: 'Display a Weixin sign-in QR code, then scan and confirm it in Weixin.',
                getQr: 'Get QR Code', checkStatus: 'Check Scan Status', ready: 'Weixin Bot Is Ready',
                readyHint: 'The backend polling service is running. You can send messages to the bot in Weixin.', scanHint: 'Scan with Weixin to sign in',
                qrFailed: 'Failed to get QR code: {message}', getQrFirst: 'Get a QR code first', querying: 'Checking...',
                pending: 'Awaiting scan...', success: 'Signed in!', expired: 'The QR code expired. Get a new one.', scanFailed: 'Scan failed. Try again.',
                loginSucceeded: 'Weixin bot signed in successfully!', queryFailed: 'Status check failed: {message}',
                logoutConfirm: 'Sign out of the Weixin bot? The polling service will stop receiving messages.',
                loggedOut: 'Signed out', logoutFailed: 'Sign-out failed: {message}'
            }
        },
        navigation: {
            dashboard: 'Resource Overview', instanceDetail: 'Instance Details', hostDetail: 'Host Details',
            inspection: 'Smart Inspection', alerts: 'Alert Management', aiSection: 'AI Agent Settings',
            aiModels: 'AI Model Management', skills: 'Skill Management', documents: 'Knowledge Base',
            evaluation: 'AI Evaluation', systemSection: 'System Settings', datasources: 'Datasource Management',
            hosts: 'Host Management', integrations: 'Integration Management', scheduledTasks: 'Task Scheduling',
            systemConfigs: 'System Parameters', users: 'User Management'
        },
        alerts: {
            title: 'Alert Management',
            embeddedNote: 'This view only shows alerts and details for this instance. Subscriptions and alert templates remain on the global Alert Management page.',
            openGlobal: 'Open Alert Management',
            tabs: { events: 'Alerts', subscriptions: 'Subscriptions', templates: 'Alert Templates' },
            loadingTemplates: 'Loading alert templates...',
            filters: {
                allDatasources: 'All data sources', allStatuses: 'All statuses', allSeverities: 'All severities',
                startTime: 'Start time', endTime: 'End time'
            },
            empty: { events: 'No alert events', subscriptions: 'No subscriptions' },
            columns: {
                severity: 'Severity', datasource: 'Datasource', faultDomain: 'Fault domain', lifecycle: 'Lifecycle',
                typeMetric: 'Type / metric', title: 'Title', startTime: 'Start time', latestTime: 'Latest occurrence',
                duration: 'Duration', status: 'Status', actions: 'Actions', time: 'Time', metricValue: 'Metric value',
                threshold: 'Threshold', notificationTargets: 'Notification targets'
            },
            actions: {
                acknowledge: 'Acknowledge', resolve: 'Resolve', silence: 'Silence', viewDetails: 'View details', edit: 'Edit',
                testNotification: 'Test notification', delete: 'Delete', close: 'Close', cancel: 'Cancel', save: 'Save'
            },
            statuses: { active: 'Active', acknowledged: 'Acknowledged', resolved: 'Resolved' },
            severity: { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' },
            event: {
                acknowledged: 'Event acknowledged', acknowledgeFailed: 'Failed to acknowledge event: {message}', resolved: 'Event resolved',
                resolveFailed: 'Failed to resolve event: {message}', recoveryTime: 'Recovery time', lastTriggeredAt: 'Last triggered at',
                durationDaysHours: '{days}d {hours}h', durationHoursMinutes: '{hours}h {minutes}m',
                durationMinutes: '{minutes}m', durationLessThanMinute: '< 1m', durationRange: 'From {start} to {end}'
            },
            diagnosis: {
                title: 'AI Diagnosis', rootCause: 'Root cause', recommendations: 'Recommended actions', inProgress: '🤖 AI diagnosis in progress...',
                timedOut: '⏳ Diagnosis timed out and is continuing in the background...', caseSummary: 'Case summary', summary: 'Diagnosis summary', suggestedActions: 'Suggested actions'
            },
            baseline: {
                comparison: 'Instance Baseline Comparison', upperBound: 'Upper bound', average: 'Average', samples: 'Samples', status: 'Status', deviation: 'Deviation',
                above: 'Above baseline', within: 'Within baseline', noProfile: 'No profile', unknown: 'Unknown'
            },
            alertTypes: {
                thresholdViolation: 'Threshold exceeded', baselineDeviation: 'Baseline deviation', customExpression: 'Custom expression',
                systemError: 'System error', aiPolicyViolation: 'AI-detected anomaly'
            },
            faultDomains: { availability: 'Availability', performance: 'Performance', storage: 'Storage', replication: 'Replication', general: 'General' },
            lifecycle: { created: 'Created', active: 'In progress', escalated: 'Escalated', acknowledged: 'Acknowledged', recovered: 'Recovered' },
            metrics: { cpu: 'CPU usage', memory: 'Memory usage', disk: 'Disk usage', activeConnections: 'Active connections', totalConnections: 'Total connections', connectionStatus: 'Connection status' },
            titles: { connectionFailure: 'Database connection failed', thresholdAlert: '{metric} threshold alert', baselineAlert: '{metric} baseline deviation alert' },
            reasons: { connectionFailure: 'Database connection failed', connectionFailureDetail: 'Database connection failed: {detail}' },
            detail: {
                title: 'Alert Details', datasourceConfig: 'Database Configuration', name: 'Name', type: 'Type', connection: 'Connection', remark: 'Notes',
                severity: 'Severity', status: 'Status', alertType: 'Alert type', time: 'Time', metric: 'Metric', currentValue: 'Current value',
                threshold: 'Threshold', triggerReason: 'Trigger reason', acknowledgedAt: 'Acknowledged at', recoveredAt: 'Recovered at', alertTitle: 'Title',
                linkedReport: 'Linked Diagnostic Report', reportFallback: 'Report #{id}', viewReport: 'View report', content: 'Details'
            },
            connectionStatus: { normal: '✅ Healthy', warning: '⚠️ Warning', failed: '❌ Failed', unknown: '❓ Unknown' },
            reportStatus: { pending: 'Pending', running: 'Generating', completed: 'Completed', failed: 'Failed' },
            subscriptions: {
                new: 'New Subscription', edit: 'Edit Subscription', all: 'All', notConfigured: 'Not configured', enabled: 'Enabled', disabled: 'Disabled',
                datasourceHint: 'Datasources (leave blank for all)', severityHint: 'Severities (leave blank for all)', targets: 'Notification targets', addTarget: 'Add target',
                targetHelp: 'Select an integration and enter target parameters such as a webhook or email address. Alert and recovery notifications are both sent by default. Password fields are submitted in ENCRYPT: format automatically.',
                enable: 'Enable subscription', select: 'Select', targetEnabled: 'Enabled', removeTarget: 'Remove target', targetParams: 'Target parameters',
                targetRequired: 'Configure at least one notification target', testConfirm: 'Send a test notification?', testSent: 'Test notification sent\n{deliveries}',
                testFailed: 'Test failed: {message}', deleteConfirm: 'Delete this subscription?', deleted: 'Subscription deleted', deleteFailed: 'Delete failed: {message}',
                saved: 'Saved', saveFailed: 'Save failed: {message}'
            },
            pagination: { previous: 'Previous', next: 'Next' },
            silence: {
                until: 'Silenced until: {time}', remaining: 'Remaining: {hours} hours', reason: 'Reason: {reason}', badge: 'Silenced · {hours}h remaining',
                current: 'Alerts are currently silenced', deadline: 'Ends at: {time}', remainingDuration: 'Time remaining: {hours} hours',
                currentReason: 'Reason: {reason}', title: 'Silence Alerts', description: 'Silence alerts for datasource {name}. Alert triggers and notifications for this datasource will be paused during this period.',
                durationLabel: 'Silence duration (hours)', durationHint: 'Default: 1 hour. Allowed range: 0.5–240 hours', reasonLabel: 'Reason (optional)',
                update: 'Update Silence', start: 'Start Silence', invalidDuration: 'Enter a valid silence duration', outOfRange: 'Silence duration must be between 0.5 and 240 hours',
                set: 'Alerts silenced for {hours} hours', setFailed: 'Failed to silence alerts: {message}'
            },
            prompt: 'Analyze the root cause of this alert event and recommend corrective actions.\n\nEvent title: {title}\nSeverity: {severity}\nAlert type: {type}\nMetric: {metric}\nAlert count: {count}',
            templates: {
                title: 'Alert Templates', create: 'New Alert Template', toolbarHint: 'Manage thresholds, baselines, and event-level AI diagnosis policies centrally. Instances only need to select a template.',
                emptyTitle: 'No alert templates', emptyHint: 'Create a template to make it available when configuring an instance.', loadFailed: 'Failed to load alert templates: {message}', loadErrorTitle: 'Load failed', selectRequired: 'Select an alert template first',
                edit: 'Edit', setDefault: 'Set as default', disable: 'Disable', enable: 'Enable', defaultBadge: 'Default template', enabledBadge: 'Enabled', disabledBadge: 'Disabled',
                noDescription: 'No description', baselineEnabled: 'Instance baseline enabled', baselineDisabled: 'Instance baseline disabled', eventAiEnabled: 'Event AI diagnosis enabled', eventAiDisabled: 'Event AI diagnosis disabled',
                name: 'Template name', description: 'Description', evaluationMode: 'Evaluation method', thresholdMode: 'Threshold evaluation', aiMode: 'AI evaluation',
                modeHint: 'Threshold evaluation is deterministic and lower cost; AI evaluation is better suited to complex trends and contextual decisions.', thresholdRules: 'Threshold rules', useCustomExpression: 'Use a custom expression',
                cpuUsage: 'CPU usage', diskUsage: 'Disk usage', activeConnections: 'Active connections', thresholdHint: 'Configure multiple alert severities for each metric, each with its own threshold, duration, and confirmation count.',
                expression: 'Expression', durationSeconds: 'Duration (seconds)', validateExpression: 'Validate expression', availableMetrics: 'Available metrics: cpu_usage, memory_usage, disk_usage, connections_active, qps, tps',
                expressionHint: 'Use this for compound conditions, such as triggering only when both CPU and active connections meet their conditions.', aiRule: 'AI evaluation policy', aiModel: 'AI evaluation model', inheritDefaultModel: 'Use default model',
                enableBaseline: 'Enable instance baseline detection', baselineHint: 'Detect significant deviations from an instance’s own history to reduce false positives from fixed thresholds.', enableEventAi: 'Enable event-level AI diagnosis and notification summaries',
                eventAiHint: 'After an alert is created or escalated, AI summarizes the symptoms, possible causes, and recommended actions.', enableTemplate: 'Enable template', setDefaultTemplate: 'Set as default template',
                createAction: 'Create', saveAction: 'Save', cancelAction: 'Cancel', editTitle: 'Edit Alert Template', createTitle: 'New Alert Template',
                nameRequired: 'Enter a template name', thresholdRequired: 'Configure at least one threshold rule or a custom expression', aiRuleRequired: 'AI evaluation templates require a natural-language policy',
                updated: 'Alert template updated', created: 'Alert template created', defaultUpdated: 'Default template updated', templateEnabled: 'Template enabled', templateDisabled: 'Template disabled',
                expressionPrefix: 'Expression: {expression}', metricLevels: '{metric} ({count} levels)', metricThreshold: '{metric}>{threshold}/{duration}s', noThreshold: 'No thresholds configured',
                enterExpression: 'Enter an expression first', validatingExpression: 'Validating expression...', expressionValid: 'Expression syntax is valid', expressionInvalid: 'Invalid expression: {message}', validationFailed: 'Validation failed: {message}',
                customExpressionRequired: 'Enter a custom expression', thresholdOrder: 'The {lower} threshold for {metric} must be lower than {upper}', baseThresholdRequired: 'Enable at least one basic threshold or switch to a custom expression', noRule: 'No policy entered',
                builtIns: {
                    standardName: 'Standard Production Alerts', standardDescription: 'Recommended for most production databases. Enables threshold alerts, instance baselines, and event-level AI diagnosis.',
                    aiName: 'AI-Powered Alerting', aiDescription: 'For scenarios where fewer hard-coded thresholds are preferred. AI makes the final decision using trends and context.',
                    devName: 'Lightweight Development Alerts', devDescription: 'For test and development environments, with more lenient thresholds and baselines disabled by default.',
                    aiPolicy: 'Determine whether the instance is clearly abnormal using CPU, disk usage, active connections, and trends from the last 15 minutes. Trigger an alert only when the anomaly persists, its impact grows, or the risk is high. Do not trigger for brief fluctuations or near-threshold values without sufficient evidence.'
                }
            }
        },
        instanceDetail: {
            sessionMeta: '{count} sessions · Last refreshed at {time}',
            loadSessionsFailed: 'Failed to load sessions: {message}',
            terminateConfirm: 'Terminate session {sessionId}? This will immediately interrupt the session.',
            terminated: 'Session {sessionId} terminated', terminateFailed: 'Failed to terminate session: {message}',
            connectionSucceeded: 'Connection successful {version}', testConnectionFailed: 'Connection test failed: {message}',
            refreshStarted: 'Refreshing metrics and collecting the latest data...', refreshFailed: 'Failed to refresh metrics: {message}',
            triggerPrompt: 'Create a manual inspection task for {name} now.',
            triggerHelp: 'The inspection will start immediately and generate a new report. When it finishes, you will be taken to Inspection Management to view the results.',
            inspectionSubmitted: 'Manual inspection task submitted{triggerId}', triggerFailed: 'Failed to trigger inspection: {message}',
            silenceSetFailed: 'Failed to set alert silence: {message}', silenceCancelFailed: 'Failed to cancel alert silence: {message}',
            topSqlCount: '{count} statements', loadTopSqlFailed: 'Failed to load TOP SQL data: {message}',
            explainFailed: 'Failed to get the execution plan: {message}',
            sessionAiTitle: 'Session AI Analysis · {name} · Session {sessionId}',
            sqlAiTitle: 'SQL AI Diagnosis · {name} · {sql}',
            sessionAnalysisTitle: 'Instance session analysis {name} #{sessionId}',
            sqlAnalysisTitle: 'SQL performance analysis {name} {sql}'
        },
        profile: {
            timezone: 'Time zone', timezonePlaceholder: 'e.g. America/New_York',
            administrator: 'Administrator', user: 'User', editProfile: 'Edit profile', changePassword: 'Change password',
            logout: 'Sign out', collapse: 'Collapse sidebar', expand: 'Expand sidebar', version: 'Version {version}',
            versionFallback: '{version} (API unavailable; using the bundled version)', username: 'Username',
            displayName: 'Display Name', displayNamePlaceholder: 'Display name (optional)', email: 'Email',
            emailPlaceholder: 'Email (optional)', phone: 'Phone', phonePlaceholder: 'Phone (optional)',
            maskedPhoneHint: 'Masked in lists as: {phone}', currentPassword: 'Current Password', newPassword: 'New Password',
            newPasswordPlaceholder: 'New password (at least 6 characters)', confirmPassword: 'Confirm New Password',
            confirmPasswordPlaceholder: 'Enter the new password again', confirmChange: 'Confirm Change', profileUpdated: 'Profile updated',
            passwordRequired: 'Complete all password fields', passwordTooShort: 'The new password must be at least 6 characters',
            passwordsMismatch: 'The new passwords do not match', passwordChanged: 'Password changed. Please sign in again',
            logoutTitle: 'Confirm Sign Out', logoutConfirm: 'Sign out of the current session?', logoutAction: 'Sign Out'
        },
        router: { notFoundTitle: 'Page not found', notFoundBody: 'The page “{page}” does not exist.' },
        status: {
            active: 'Active', inactive: 'Inactive', running: 'Running', pending: 'Pending', completed: 'Completed',
            failed: 'Failed', healthy: 'Healthy', unhealthy: 'Unhealthy', connected: 'Connected',
            disconnected: 'Disconnected', critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low', info: 'Info'
        },
        dashboard: {
            loadFailed: 'Load failed', loadAlertFailed: 'Could not load alert details: {message}',
            noDatasources: 'No datasources', addDatasourcePrompt: 'Add a database connection to start monitoring and diagnosis',
            addDatasource: 'Add datasource', needsAttention: 'Needs attention', otherResources: 'Other resources',
            allStatuses: 'All statuses', allTypes: 'All types', allHosts: 'All hosts', searchPlaceholder: 'Search name/address...',
            hostHealth: 'Host health', online: 'Online', abnormal: 'Abnormal', allOnline: 'All online',
            moreAbnormalHosts: '+{count} unhealthy hosts',
            activeAlerts: 'Active alerts', viewAllAlerts: 'View all {count} alerts →', systemHealthy: 'System operating normally',
            datasourceHealth: 'Datasource health', healthy: 'Healthy', unhealthyDatasources: 'Unhealthy datasources',
            healthyDatasources: 'Healthy datasources', datasourceFallback: 'Datasource #{id}',
            moreUnhealthyDatasources: '+{count} unhealthy', moreDatasources: '+{count} datasources',
            noMatchingResources: 'No matching resources', activeConnections: 'Active connections', lastUpdated: 'Last updated {time}',
            health: { connectionFailed: 'Connection failed', healthy: 'Healthy', warning: 'Warning', abnormal: 'Abnormal', unknown: 'Unknown' },
            hostReasons: {
                offline: 'Connection failed or monitoring data interrupted', error: 'Core metrics exceeded thresholds',
                warning: 'Core metrics near thresholds', unknown: 'Abnormal status', staleMetrics: 'Connection failed (no data received for over 5 minutes)',
                noMetrics: 'No monitoring data', normal: 'Operating normally', cpu: 'CPU', memory: 'Memory', disk: 'Disk',
                metricTooHigh: '{metric} usage is too high ({value})', metricHigh: '{metric} usage is high ({value})'
            }
        },
        hostDetail: {
            title: 'Host Details', noHosts: 'No hosts',
            noHostsHint: 'Add a host before opening the host operations workspace.', goToHosts: 'Go to Host Management',
            hostList: 'Hosts', workbench: 'Host Operations Workspace', searchHosts: 'Search host name or address',
            noMatchingHosts: 'No matching hosts', loadFailed: 'Failed to load: {message}',
            status: { critical: 'Critical', warning: 'Warning', offline: 'Offline', normal: 'Healthy', unknown: 'Unknown' },
            tabs: {
                info: 'Overview', monitor: 'Performance', processes: 'Processes', terminal: 'Terminal',
                network: 'Network Topology', ai: 'AI Diagnosis'
            },
            uptime: '{days}d {hours}h {minutes}m',
            refreshConfig: 'Refresh configuration', refreshing: 'Refreshing...', collectedAt: 'Collected at: {time}',
            configRefreshed: 'Configuration refreshed', refreshFailed: 'Refresh failed: {message}',
            systemInfo: 'System Information', hostname: 'Hostname', operatingSystem: 'Operating System',
            systemVersion: 'OS Version', kernelVersion: 'Kernel Version', uptimeLabel: 'Uptime', loadAverage: 'Load Average',
            cpuInfo: 'CPU Information', processorModel: 'Processor Model', physicalCpuCount: 'Physical CPUs',
            logicalCoreCount: 'Logical Cores', cpuFrequency: 'CPU Frequency', memoryInfo: 'Memory Information',
            totalMemory: 'Total Memory', usedMemory: 'Used Memory', availableMemory: 'Available Memory',
            buffers: 'Buffers', cache: 'Cache', swap: 'Swap', diskInfo: 'Disk Information',
            filesystem: 'Filesystem', mountPoint: 'Mount Point', totalCapacity: 'Total', used: 'Used',
            available: 'Available', usage: 'Usage', noDiskInfo: 'No disk information', networkInterfaces: 'Network Interfaces',
            interfaceName: 'Interface', addressFamily: 'Address Family', ipAddress: 'IP Address',
            noNetworkInterfaces: 'No network interface information', unavailable: 'N/A',
            configUnavailable: 'Host configuration unavailable', historicalMetricsOnly: 'Historical metrics are available, but an SSH connection cannot currently be established',
            hostUnreachable: 'The host is unreachable and no monitoring data is available', retryConnection: 'Retry connection',
            retrying: 'Retrying...', errorInfo: 'Error: {message}', latestMetricAt: 'Latest metric: {time}',
            performanceMonitoring: 'Performance Monitoring', ranges: {
                minute1: 'Last minute', minute10: 'Last 10 minutes', hour1: 'Last hour',
                hour6: 'Last 6 hours', day1: 'Last 24 hours', day7: 'Last 7 days',
                month1: 'Last month', custom: 'Custom range'
            },
            cpuUsage: 'CPU Usage', memoryUsage: 'Memory Usage', diskUsage: 'Disk Usage',
            unknownValue: 'Unknown', lastUpdated: 'Last updated: {time}', basicMetrics: 'Core Metrics',
            memoryUsageRate: 'Memory Usage', diskUsageRate: 'Disk Usage', loadAverage1m: 'Load Average (1 min)',
            diskAndNetworkIo: 'Disk and Network I/O', diskIops: 'Disk IOPS (Read/Write)',
            diskIoThroughput: 'Disk I/O Throughput (Read/Write KB/s)', networkIoThroughput: 'Network Throughput (Receive/Send KB/s)',
            read: 'Read', write: 'Write', receive: 'Receive', send: 'Send',
            processSearch: 'Search processes...', user: 'User', state: 'State', command: 'Command', processDetails: 'Process Details',
            startTime: 'Start Time', virtualMemory: 'Virtual Memory', residentMemory: 'Resident Memory',
            cpuTime: 'CPU Time', workingDirectory: 'Working Directory', commandDetails: 'Command Details',
            fullCommandLine: 'Full Command Line', diskIo: 'Disk I/O', readBytes: 'Bytes Read',
            writeBytes: 'Bytes Written', readChars: 'Characters Read', writeChars: 'Characters Written',
            readSyscalls: 'Read System Calls', writeSyscalls: 'Write System Calls', networkConnections: 'Network Connections',
            localAddress: 'Local Address', localPort: 'Local Port', remoteAddress: 'Remote Address', remotePort: 'Remote Port',
            receiveQueue: 'Receive Queue', sendQueue: 'Send Queue', bytes: '{count} bytes',
            noActiveConnections: 'No active network connections', environmentPreview: 'Environment Variables (first 20)',
            processLoadFailed: 'Failed to load process details: {message}', closeProcessDetails: 'Close process details',
            diagnosisSessionTitle: 'Host Diagnosis: {host}', customRangeTitle: 'Custom Time Range',
            rangeStart: 'Start Time', rangeEnd: 'End Time', selectRange: 'Select a start and end time',
            invalidRange: 'The start time must be earlier than the end time', dataLoadFailed: 'Failed to load data: {message}',
            noDataInRange: 'No data is available for the selected time range', customRangeLoaded: 'Custom time range loaded',
            toggleSidebar: 'Expand or collapse the host list',
            terminalView: {
                title: 'Terminal Session', clear: 'Clear terminal', reconnect: 'Reconnect', connecting: 'Connecting to host...',
                connected: 'Connected!', error: 'Error: {message}', connectionError: 'Connection error', disconnected: 'Disconnected'
            },
            networkView: {
                loading: 'Loading network topology...', refreshNow: 'Refresh Now', host: 'Host', waitingForData: 'Waiting for data...',
                noConnections: 'No network connections observed', pollingHint: 'Polling will continue and the topology will appear when a connection is established.',
                hotConnections: 'Top Connections', sortedByConnections: 'Sorted by connection count', loadFailed: 'Failed to load network topology',
                loadFailedWithMessage: 'Failed to load network topology: {message}', status: 'Network Topology · Updated {time} · Auto-refresh every {seconds}s',
                totalConnections: 'Total Connections', connectionStatus: 'Connection Status', established: 'Established', waiting: 'Waiting',
                listening: 'Listening', remoteNodes: 'Remote Nodes', waitingForNetworkData: 'Waiting for network data',
                establishedConnections: 'Established Connections', listeningPorts: 'Listening Ports',
                hiddenNodes: 'Showing the top {visible} nodes; {hidden} more appear in the list',
                waitingForRanking: 'Connection rankings will appear when network activity is detected', connections: '{count} connections',
                nodeDetails: 'Network Node Details · {ip}', remoteIp: 'Remote IP', connectionCount: 'Connections',
                stateDistribution: 'Connection State Distribution', noStateData: 'No state data', other: 'Other'
            }
        },
        users: {
            newUser: 'New user', deleteTitle: 'Delete user',
            deleteConfirm: 'Are you sure you want to delete user “{username}”? This action cannot be undone.', deleted: 'User deleted',
            noLoginLogs: 'No sign-in history', loginLogsTitle: 'Sign-in history for {username}', loadLoginLogsFailed: 'Could not load sign-in history: {message}',
            resetFor: 'Reset password for {username}', passwordReset: 'Password reset successfully', credentialsRequired: 'Username and password are required'
        },
        chat: {
            noActiveSession: 'No active session', fileTooLarge: 'File too large (max 10MB)', uploadFailed: 'Failed to upload file: {message}',
            uploadError: 'Upload failed', attached: 'File attached', createSessionFailed: 'Failed to create session: {message}',
            clearSessionFailed: 'Failed to clear session: {message}', deleteSessionFailed: 'Failed to delete session: {message}',
            sessionCleared: 'Session cleared', sessionDeleted: 'Session deleted', generationStopped: 'Generation stopped'
        },
        datasourceSelector: {
            select: 'Select a datasource', all: 'All datasources', connectionHealthy: 'Connection healthy',
            connectionUnhealthy: 'Connection unhealthy', connectionWarning: 'Connection warning', statusUnknown: 'Status unknown',
            selectedCount: '{count} selected', loadFailed: 'Failed to load datasources', searchPlaceholder: 'Search datasources...',
            searchLabel: 'Search datasources', noMatches: 'No matching datasources', noData: 'No datasources',
            noFilter: 'Do not filter by datasource', current: 'Current', address: 'Address', selected: 'Selected'
        },
        datasourceForm: {
            name: 'Datasource Name', namePlaceholder: 'My database', databaseType: 'Database Type', port: 'Port',
            host: 'Host Address', username: 'Username', password: 'Password', keepPassword: '(keep unchanged)', database: 'Database Name',
            tags: 'Tags', tagsPlaceholder: 'e.g. production, membership, core system', tagsHint: 'Separate multiple tags with commas',
            remark: 'Notes', remarkPlaceholder: 'Optional business context or special configuration', remarkHint: 'These notes are automatically included in AI diagnosis',
            connectionMode: 'Connection Mode', defaultMode: 'Default', oracleModeHint: 'Connect as SYSDBA/SYSOPER (corresponding privileges required)',
            relatedHost: 'Related Host (optional)', monitoringSource: 'Monitoring Data Source', directCollection: 'System collection (direct database connection)',
            integrationCollection: 'Integration collection (external system)', monitoringSourceHint: 'Choose how monitoring data is collected',
            inboundIntegration: 'Inbound Integration', inboundIntegrationHint: 'Select an inbound_metric integration to retrieve external metrics',
            select: 'Select', collectionParams: 'Collection Parameters', update: 'Update', create: 'Create', cancel: 'Cancel',
            integrationRequired: 'Select an inbound integration when using integration collection', externalIdRequired: 'This integration requires an external instance ID',
            updated: 'Datasource updated', created: 'Datasource created', testConnection: 'Test Connection',
            connectionSuccess: 'Connected! {version}', connectionFailed: 'Connection failed: {message}', testFailed: 'Test failed: {message}',
            editTitle: 'Edit Datasource', createTitle: 'New Datasource', externalId: 'External Instance ID',
            externalIdPlaceholder: 'e.g. an instance ID from a cloud provider or external monitoring system',
            externalIdHelp: 'The instance identifier in the external monitoring system. Whether it is required depends on the selected integration.',
            initialExternalIdHelp: 'The instance identifier in the external monitoring system. It is usually required for Huawei Cloud and Alibaba Cloud RDS.',
            huaweiId: 'Huawei Cloud RDS Instance ID *', huaweiIdPlaceholder: 'e.g. 8ad0f7d4c0f74f7e9c0f4d8f3b1e2a6din01',
            huaweiIdHelp: 'Enter the Huawei Cloud RDS instance ID. region_id locates the CES/IAM endpoint; AK/SK are read from system parameters.',
            aliyunId: 'Alibaba Cloud RDS Instance ID *', aliyunIdPlaceholder: 'e.g. rm-uf6wjk5xxxxxxx',
            aliyunIdHelp: 'Enter the Alibaba Cloud RDS instance ID. AccessKey values may be read from system settings.',
            tencentId: 'Tencent Cloud Instance ID *',
            tencentIdPlaceholder: 'MySQL: cdb-xxx; PostgreSQL/SQL Server: postgres-xxx / mssql-xxx; TDSQL-C: cynosdbmysql-ins-xxx',
            tencentIdHelp: 'Enter the instance identifier used by Tencent Cloud Monitor. MySQL/TDSQL-C normally use InstanceId; PostgreSQL/SQL Server use resourceId. SecretId/SecretKey are read from system parameters.',
            huaweiParams: 'These parameters call Huawei Cloud CES/IAM APIs; they are not database connection settings. region_id is still required, while AK/SK are read from system parameters.',
            aliyunParams: 'These parameters call Alibaba Cloud RDS APIs; they are not database connection settings.',
            tencentParams: 'These parameters call Tencent Cloud Monitor APIs; they are not database connection settings. SecretId/SecretKey are read from system parameters, so only values such as region_id are needed here. Standard regions such as ap-guangzhou and documented aliases such as gz/1 are supported. For MySQL read-only or proxy nodes, mysql_instance_type may also be set.',
            genericParams: 'These parameters call an external monitoring integration; they are not database connection settings.'
        },
        dataTable: {
            page: 'Page', more: 'More', to: 'to', of: 'of', next: 'Next', last: 'Last', first: 'First',
            previous: 'Previous', loading: 'Loading...', noRows: 'No data', search: 'Search...', blanks: 'Blanks',
            filter: 'Filter...', gridUnavailable: 'AG Grid failed to load. Refresh the page.', renderFailed: 'Failed to render table: {message}'
        },
        scheduledTasks: {
            descriptionPlaceholder: 'e.g. Run the inspection script every night to check instance status and produce a summary.',
            hourlyMinuteTitle: 'Minute within the hour', minuteSecondTitle: 'Second within the minute',
            removeTarget: 'Remove notification target'
        },
        aiModels: { reasoningEffort: 'Reasoning strength: {value}' },
        skills: {
            loading: 'Loading skills...', loadError: 'Could not load skills', retry: 'Retry', builtIn: 'Built-in',
            view: 'View', test: 'Test', edit: 'Edit', export: 'Export', exportFailed: 'Could not export skill', delete: 'Delete', required: 'required',
            filterFailed: 'Could not filter skills', searchFailed: 'Skill search failed', description: 'Description',
            parameters: 'Parameters', permissions: 'Permissions', code: 'Code', loadDetailsFailed: 'Could not load skill details',
            selectDatasource: 'Select datasource', multiSelectHint: 'Hold Ctrl/Cmd to select multiple', select: 'Select',
            jsonFormat: 'JSON format', testTitle: 'Test {name}', execute: 'Execute', executing: 'Executing...',
            result: 'Result', invalidJson: 'Invalid JSON for parameter {name}', loadFailed: 'Could not load skill',
            enabled: 'Skill enabled', disabled: 'Skill disabled', toggleFailed: 'Could not update skill status',
            deleteConfirm: 'Are you sure you want to delete this skill?', deleted: 'Skill deleted', deleteFailed: 'Could not delete skill',
            importTitle: 'Import skill', yamlFile: 'YAML file', import: 'Import', importFailed: 'Could not import skill: {message}',
            imported: 'Skill imported successfully', createTitle: 'Create new skill', skillId: 'Skill ID',
            idHint: 'Lowercase letters, numbers, and underscores only', name: 'Name', version: 'Version',
            versionHint: 'Semantic versioning (major.minor.patch)', category: 'Category', tags: 'Tags',
            describePlaceholder: 'Describe what this skill does', tagsPlaceholder: 'e.g. mysql, performance, slow-query (comma-separated)',
            timeout: 'Timeout (seconds)', defaultSeconds: 'Default: 30',
            timeoutHint: 'Maximum execution time (1-300 seconds)', parametersJson: 'Parameters (JSON)', parametersHint: 'Array of parameter definitions',
            codeHint: 'Python async function code', create: 'Create skill', cancel: 'Cancel', paramsMustArray: 'Parameters must be an array',
            invalidParameters: 'Invalid parameters JSON: {message}', created: 'Skill created successfully', createFailed: 'Could not create skill: {message}',
            editTitle: 'Edit skill: {name}', immutableId: 'ID cannot be changed', commaSeparated: 'comma-separated',
            saveChanges: 'Save changes', updated: 'Skill updated successfully', updateFailed: 'Could not update skill: {message}',
            categories: {
                generalDiagnostics: 'General Diagnostics', platformOperations: 'Platform Operations', knowledgeRetrieval: 'Knowledge Retrieval',
                privilegedOperations: 'Privileged Operations', mysql: 'MySQL', oceanbaseMysql: 'OceanBase MySQL',
                postgresql: 'PostgreSQL', sqlServer: 'SQL Server', oracle: 'Oracle', openGauss: 'openGauss',
                sapHana: 'SAP HANA', monitoring: 'Monitoring', inspection: 'Inspection', notification: 'Notifications',
                query: 'Queries', custom: 'Custom'
            }
        },
        skillAuthorization: {
            title: 'Skill Authorization', emptyGroups: 'No configurable skill authorization groups are available', builtIn: 'Built-in',
            allowed: 'Allowed', denied: 'Denied', emptyItems: 'No items to display', apply: 'Apply authorization',
            help: 'Control which skill categories the AI may call during diagnosis. Changes take effect immediately for the current session and reset after a refresh or session switch.',
            updated: 'Skill authorization updated for the current session. It will reset after a refresh or session switch.',
            groups: {
                platform_operations: { label: 'Platform Operations', description: 'Allow the AI to manage platform resources such as datasources, hosts, skills, and alert settings.' },
                high_privilege_operations: { label: 'Privileged Operations', description: 'Allow the AI to perform high-risk changes such as arbitrary SQL or operating-system commands.' },
                knowledge_retrieval: { label: 'Knowledge Retrieval', description: 'Allow the AI to use knowledge-retrieval skills and built-in diagnostic document tools.' }
            },
            items: {
                list_documents: { description: 'Browse the built-in diagnostic document catalog.' },
                read_document: { description: 'Read the full content of a built-in diagnostic document.' }
            }
        },
        inspection: { listMeta: '{total} reports · Page {page}' },
        configDescriptions: {
            inspection_dedup_window_minutes: 'Inspection trigger deduplication window in minutes',
            default_alert_engine_mode: 'Default alert engine mode: threshold or ai',
            ai_alert_timeout_seconds: 'AI alert evaluation timeout in seconds',
            ai_alert_confidence_threshold: 'Minimum AI alert confidence threshold (0-1)',
            notification_cooldown_minutes: 'Notification cooldown window in minutes for alerts of the same type',
            monitoring_collection_interval_seconds: 'Global monitoring collection interval in seconds',
            network_probe_host: 'Network probe target address',
            app_external_base_url: 'External base URL used to generate notification detail links',
            smtp_host: 'SMTP server address', smtp_port: 'SMTP server port', smtp_username: 'SMTP username',
            smtp_password: 'SMTP password', smtp_from_email: 'Sender email address', smtp_use_tls: 'Enable STARTTLS encryption',
            aliyun_access_key_id: 'Alibaba Cloud AccessKey ID', aliyun_access_key_secret: 'Alibaba Cloud AccessKey Secret',
            tencentcloud_secret_id: 'Tencent Cloud SecretId', tencentcloud_secret_key: 'Tencent Cloud SecretKey'
        }
    };
})(window);
