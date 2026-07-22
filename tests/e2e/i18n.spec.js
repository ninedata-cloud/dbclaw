const { test, expect } = require('@playwright/test');

async function expectNoChineseUi(page, rootSelector, context) {
    const leaks = await page.locator(rootSelector).evaluate(root => {
        const han = /[\p{Script=Han}]/u;
        const results = [];
        const add = (kind, element, value) => {
            const text = String(value || '').trim();
            if (!text || !han.test(text)) return;
            results.push(`${kind} <${element.tagName.toLowerCase()}>: ${text}`);
        };

        add('text', root, root.innerText);
        for (const element of [root, ...root.querySelectorAll('*')]) {
            for (const attr of ['placeholder', 'title', 'aria-label']) {
                if (element.hasAttribute?.(attr)) add(attr, element, element.getAttribute(attr));
            }
            if (element.tagName === 'INPUT' && ['button', 'submit', 'reset'].includes(element.type)) {
                add('value', element, element.value);
            }
            for (const pseudo of ['::before', '::after']) {
                const content = getComputedStyle(element, pseudo).content;
                if (content && content !== 'none' && content !== 'normal') add(pseudo, element, content);
            }
        }
        return results;
    });
    expect(leaks, `${context}: ${leaks.join('\n')}`).toEqual([]);
}

test('first visit defaults to Chinese and login locale persists locally', async ({ browser }) => {
    const context = await browser.newContext({ locale: 'en-US' });
    const page = await context.newPage();
    await page.goto('/index.html#login');
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
    await expect(page.locator('#login-btn')).toHaveText('登录');

    await page.locator('.login-language-select').selectOption('en-US');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en-US');
    await expect(page.locator('#login-btn')).toHaveText('Sign in');
    await page.reload();
    await expect(page.locator('#login-btn')).toHaveText('Sign in');
    await context.close();
});

test('date picker follows the application locale and preserves machine-readable values', async ({ page }) => {
    await page.goto('/index.html#login');
    await page.evaluate(() => {
        I18n.setLocale('zh-CN', { persist: false });
        const fixture = document.createElement('div');
        fixture.id = 'date-picker-fixture';
        fixture.style.cssText = 'position:fixed;top:12px;left:12px;z-index:2000;width:220px';
        fixture.innerHTML = '<input id="date-picker-test" type="date" value="2026-07-22" data-date-picker>';
        document.body.appendChild(fixture);
        DatePicker.enhanceAll(fixture);
    });

    const trigger = page.locator('#date-picker-fixture .date-picker-trigger');
    await expect(trigger).toContainText('2026/07/22');
    await trigger.click();
    await expect(page.locator('.date-picker-title')).toHaveText('2026年7月');
    await expect(page.locator('.date-picker-weekday').first()).toHaveText('周一');
    await expect(page.locator('.date-picker-footer')).toContainText('今天');

    await page.evaluate(() => I18n.setLocale('en-US', { persist: false }));
    await expect(trigger).toContainText('07/22/2026');
    await expect(page.locator('.date-picker-title')).toHaveText('July 2026');
    await expect(page.locator('.date-picker-weekday').first()).toHaveText('Sun');
    await expect(page.locator('.date-picker-footer')).toContainText('Today');
    await expect(page.locator('.date-picker-popover')).toHaveAttribute('lang', 'en-US');

    await page.getByRole('button', { name: 'Wednesday, July 22, 2026' }).click();
    await expect(page.locator('.date-picker-popover')).toBeHidden();
    await expect(page.locator('#date-picker-test')).toHaveValue('2026-07-22');
});

test('account locale drives the shell and dirty state guards route refresh', async ({ page }) => {
    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/login') {
            return route.fulfill({ json: { user: {
                id: 1, username: 'admin', display_name: 'Admin', email: null, phone: null,
                locale: 'en-US', is_active: true, is_admin: true
            } } });
        }
        if (url.pathname === '/api/auth/me/locale') {
            const request = route.request().postDataJSON();
            return route.fulfill({ json: {
                id: 1, username: 'admin', display_name: 'Admin', email: null, phone: null,
                locale: request.locale, is_active: true, is_admin: true
            } });
        }
        if (url.pathname === '/api/app/info') return route.fulfill({ json: { app_version: 'test' } });
        return route.fulfill({ json: [] });
    });

    await page.goto('/index.html#login');
    await page.locator('#login-username').fill('admin');
    await page.locator('#login-password').fill('password');
    await page.locator('#login-btn').click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en-US');
    await expect(page.locator('[data-page="dashboard"] span')).toHaveText('Resource Overview');

    await page.locator('.sidebar-user-info').click();
    await page.locator('.sidebar-language-select').click();
    await expect(page.locator('#sidebar-user-menu')).toBeVisible();
    await page.evaluate(() => DirtyState.mark('page'));
    page.once('dialog', dialog => dialog.dismiss());
    await page.locator('.sidebar-language-select').selectOption('zh-CN');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en-US');

    page.once('dialog', dialog => dialog.accept());
    await page.locator('.sidebar-language-select').selectOption('zh-CN');
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
    await expect(page.locator('[data-page="dashboard"] span')).toHaveText('资源大盘');
});

test('empty-state console pages render without Chinese UI text in English mode', async ({ page }) => {
    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/login') {
            return route.fulfill({ json: { user: {
                id: 1, username: 'admin', display_name: 'Admin', email: null, phone: null,
                locale: 'en-US', is_active: true, is_admin: true
            } } });
        }
        if (url.pathname === '/api/app/info') return route.fulfill({ json: { app_version: 'test' } });
        if (url.pathname === '/api/skills/categories') return route.fulfill({ json: { categories: [] } });
        if (url.pathname === '/api/alerts/events') return route.fulfill({ json: { events: [], total: 0 } });
        return route.fulfill({ json: [] });
    });
    await page.goto('/index.html#login');
    await page.locator('#login-username').fill('admin');
    await page.locator('#login-password').fill('password');
    await page.locator('#login-btn').click();

    for (const route of [
        'dashboard', 'datasources', 'hosts', 'alerts', 'inspection', 'ai-models',
        'documents', 'skills', 'evaluation', 'integrations', 'system-configs',
        'scheduled-tasks', 'users'
    ]) {
        await page.evaluate(value => Router.navigate(value), route);
        await page.waitForTimeout(75);
        await expectNoChineseUi(page, '#page-content', route);
    }
});

test('Inspection localizes historical report metadata and all trigger filters', async ({ page }) => {
    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/login') {
            return route.fulfill({ json: { user: {
                id: 1, username: 'admin', display_name: 'Admin', email: null, phone: null,
                locale: 'en-US', is_active: true, is_admin: true
            } } });
        }
        if (url.pathname === '/api/app/info') return route.fulfill({ json: { app_version: 'test' } });
        if (url.pathname === '/api/datasources') {
            return route.fulfill({ json: [
                { id: 1, name: 'opengauss_5.0(58)', db_type: 'opengauss', host: '127.0.0.1', port: 5432 },
                { id: 2, name: 'mysql_5.5(71:3306)', db_type: 'mysql', host: '127.0.0.1', port: 3306 },
            ] });
        }
        if (url.pathname === '/api/inspections/reports') {
            return route.fulfill({ json: { report: [
                {
                    report_id: 2474, datasource_name: 'opengauss_5.0(58)',
                    title: '连接失败巡检 - opengauss_5.0(58)', trigger_type: 'connection_failure',
                    trigger_reason: 'Database connection failed: opengauss_5.0(58) (opengauss)',
                    created_at: '2026-07-22T10:51:59Z', status: 'completed', error_message: null,
                },
                {
                    report_id: 2475, datasource_name: 'mysql_5.5(71:3306)',
                    title: '手动巡检 - mysql_5.5(71:3306)', trigger_type: 'manual',
                    trigger_reason: '人工触发巡检', created_at: '2026-07-22T11:32:59Z',
                    status: 'completed', error_message: null,
                },
            ], total: 2 } });
        }
        return route.fulfill({ json: [] });
    });

    await page.goto('/index.html#login');
    await page.locator('#login-username').fill('admin');
    await page.locator('#login-password').fill('password');
    await page.locator('#login-btn').click();
    await page.waitForURL('**#dashboard');
    await page.evaluate(() => Router.navigate('inspection'));

    await expect(page.locator('.inspection-table tbody tr')).toHaveCount(2);
    await expect(page.locator('.inspection-col-title').nth(1)).toContainText('Connection Failure Inspection - opengauss_5.0(58)');
    await expect(page.locator('.inspection-col-title').nth(2)).toContainText('Manual Inspection - mysql_5.5(71:3306)');
    await expect(page.locator('.inspection-col-trigger').nth(1)).toContainText('Connection failure');
    await expect(page.locator('.inspection-col-reason').nth(2)).toContainText('Manual inspection');
    await expect(page.locator('#filterTriggerType option')).toHaveText([
        'All trigger types', 'Manual', 'Scheduled', 'Anomaly', 'Connection failure', 'Baseline deviation'
    ]);
    await expectNoChineseUi(page, '#page-content', 'populated inspection reports');
});

test('Alert Management localizes populated events, subscriptions, templates, and dialogs', async ({ page }) => {
    let savedTemplatePayload = null;
    const templateConfig = {
        alert_engine_mode: 'ai',
        threshold_rules: {
            cpu_usage: { levels: [{ severity: 'critical', threshold: 90, duration: 60 }] },
            disk_usage: { levels: [{ severity: 'critical', threshold: 95, duration: 60 }] },
        },
        baseline_config: { enabled: true },
        event_ai_config: { enabled: true },
        ai_policy_text: '请结合 CPU、磁盘使用率、活跃连接数及最近 15 分钟趋势判断该实例是否处于明显异常状态。只有在异常持续、影响扩大或风险较高时才触发告警；若只是短时抖动或接近阈值但证据不足，则不触发告警。',
    };
    const event = {
        id: 10, datasource_id: 1, severity: 'critical', status: 'active',
        fault_domain: 'performance', lifecycle_stage: 'escalated', alert_type: 'threshold_violation',
        metric_name: 'cpu_usage', title: 'CPU 使用率阈值告警', alert_count: 2,
        event_started_at: '2026-07-22T08:00:00Z', event_ended_at: '2026-07-22T09:15:00Z',
        root_cause: 'A batch workload saturated the CPU.', recommended_actions: 'Reduce batch concurrency.',
        datasource_silence_until: '2099-07-22T10:00:00Z', datasource_silence_reason: 'Maintenance window',
    };

    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/login') {
            return route.fulfill({ json: { user: {
                id: 1, username: 'admin', display_name: 'Admin', email: null, phone: null,
                locale: 'en-US', is_active: true, is_admin: true
            } } });
        }
        if (url.pathname === '/api/app/info') return route.fulfill({ json: { app_version: 'test' } });
        if (url.pathname === '/api/datasources') {
            return route.fulfill({ json: [{ id: 1, name: 'primary-db', host: '127.0.0.1', port: 5432, database: 'dbclaw', db_type: 'postgresql' }] });
        }
        if (url.pathname === '/api/alerts/events') return route.fulfill({ json: { events: [event], total: 1 } });
        if (url.pathname === '/api/alerts/events/10/alerts') {
            return route.fulfill({ json: { alerts: [{
                id: 20, status: 'active', severity: 'critical', alert_type: 'threshold_violation',
                metric_name: 'cpu_usage', metric_value: 96, threshold_value: 90,
                created_at: '2026-07-22T09:15:00Z', title: 'CPU 使用率阈值告警', content: 'CPU usage exceeded its threshold.',
                diagnosis_context: {
                    datasource_info: { name: 'primary-db', db_type: 'postgresql', host: '127.0.0.1', port: 5432, database: 'dbclaw', connection_status: 'normal' },
                    case_summary: 'Sustained CPU pressure', diagnosis_summary: 'A batch job is consuming CPU.',
                    root_cause: 'Batch concurrency is too high.', recommended_action: 'Reduce concurrency.',
                    linked_report: { report_id: 30, title: '异常巡检 - primary-db', trigger_type: 'anomaly', status: 'completed', created_at: '2026-07-22T09:20:00Z' }
                }
            }] } });
        }
        if (url.pathname === '/api/alerts/events/10/context') {
            return route.fulfill({ json: { baseline_comparisons: [{
                metric_name: 'cpu_usage', current_value: 96, baseline_p95: 62, upper_bound: 78,
                baseline_avg: 50, sample_count: 48, status: 'above_baseline', deviation_ratio: 1.92
            }] } });
        }
        if (url.pathname === '/api/alerts/subscriptions/list') {
            return route.fulfill({ json: [{
                id: 40, datasource_ids: [1], severity_levels: ['critical', 'high'], enabled: true,
                integration_targets: [{ target_id: 'mail', integration_id: 50, name: 'DBA email', enabled: true, params: {} }]
            }] });
        }
        if (url.pathname === '/api/integrations') {
            return route.fulfill({ json: [{
                id: 50, integration_id: 'builtin_email', name: 'Mail通知', integration_type: 'outbound_notification', enabled: true,
                config_schema: {
                    type: 'object',
                    properties: {
                        to: { type: 'string', title: '收件人', description: '收件人邮箱地址，多个用逗号分隔' },
                        cc: { type: 'string', title: '抄送（可选）', description: '抄送邮箱地址，多个用逗号分隔' }
                    },
                    required: ['to']
                }
            }] });
        }
        if (url.pathname === '/api/inspections/templates') {
            return route.fulfill({ json: [
                {
                    id: 59, name: '标准生产告警',
                    description: '适合大多数生产库，启用阈值告警、实例基线和事件级 AI 诊断。',
                    enabled: true, is_default: true,
                    template_config: { ...templateConfig, alert_engine_mode: 'threshold', ai_policy_text: null }
                },
                {
                    id: 60, name: 'AI 智能判警',
                    description: '适合希望减少硬编码阈值的场景，由 AI 结合趋势与上下文做最终判警。',
                    enabled: true, is_default: false, template_config: templateConfig
                },
                {
                    id: 61, name: '轻量开发告警',
                    description: '适合测试/开发环境，阈值更宽松，默认关闭基线。',
                    enabled: true, is_default: false,
                    template_config: { ...templateConfig, alert_engine_mode: 'threshold', baseline_config: { enabled: false }, ai_policy_text: null }
                }
            ] });
        }
        if (url.pathname === '/api/inspections/templates/60' && route.request().method() === 'PUT') {
            savedTemplatePayload = route.request().postDataJSON();
            return route.fulfill({ json: { id: 60, ...savedTemplatePayload } });
        }
        if (url.pathname === '/api/ai-models') return route.fulfill({ json: [{ id: 70, name: 'diagnosis-model' }] });
        return route.fulfill({ json: [] });
    });

    await page.goto('/index.html#login');
    await page.locator('#login-username').fill('admin');
    await page.locator('#login-password').fill('password');
    await page.locator('#login-btn').click();
    await page.waitForURL('**#dashboard');
    await page.evaluate(() => Router.navigate('alerts'));
    await expect(page.locator('.events-table')).toBeVisible();
    await expectNoChineseUi(page, '#page-content', 'populated alert events');

    await page.locator('.expand-icon').click();
    await expect(page.locator('.nested-alerts-table')).toBeVisible();
    await expectNoChineseUi(page, '#page-content', 'expanded alert event');
    await page.locator('.nested-alerts-table .btn-icon').click();
    await expect(page.locator('#modal-overlay')).toBeVisible();
    await expectNoChineseUi(page, '#modal-container', 'alert details dialog');
    await page.getByRole('button', { name: 'Close' }).click();

    await page.getByRole('button', { name: 'Subscriptions', exact: true }).click();
    await expect(page.locator('.subscriptions-list')).toBeVisible();
    await expectNoChineseUi(page, '#page-content', 'subscriptions list');
    await page.getByRole('button', { name: 'New Subscription' }).click();
    await expect(page.locator('.target-integration option:checked')).toHaveText('Email Notification');
    await expect(page.locator('.target-param-label')).toHaveText(['Recipient*', 'CC (optional)']);
    await expect(page.locator('.target-param[data-key="to"]')).toHaveAttribute('placeholder', 'Recipient email addresses, separated by commas');
    await expect(page.locator('.target-param[data-key="cc"]')).toHaveAttribute('placeholder', 'CC email addresses, separated by commas');
    await expectNoChineseUi(page, '#modal-container', 'subscription dialog');
    await page.locator('#modal-container .modal-header .btn-icon').click();

    await page.getByRole('button', { name: 'Alert Templates', exact: true }).click();
    await expect(page.locator('#templates-pane')).toContainText('Standard Production Alerts');
    await expect(page.locator('#templates-pane')).toContainText('AI-Powered Alerting');
    await expect(page.locator('#templates-pane')).toContainText('Lightweight Development Alerts');
    await expectNoChineseUi(page, '#page-content', 'alert template cards');
    const aiTemplateCard = page.locator('.datasource-card').filter({ hasText: 'AI-Powered Alerting' });
    await aiTemplateCard.getByRole('button', { name: 'Edit' }).click();
    await expect(page.locator('[name="name"]')).toHaveValue('AI-Powered Alerting');
    await expect(page.locator('[name="ai_policy_text"]')).not.toHaveValue(/[\p{Script=Han}]/u);
    await expectNoChineseUi(page, '#modal-container', 'alert template dialog');
    await page.locator('#modal-container').getByRole('button', { name: 'Save', exact: true }).click();
    await expect.poll(() => savedTemplatePayload).not.toBeNull();
    expect(savedTemplatePayload.name).toBe('AI 智能判警');
    expect(savedTemplatePayload.description).toBe('适合希望减少硬编码阈值的场景，由 AI 结合趋势与上下文做最终判警。');
    expect(savedTemplatePayload.template_config.ai_policy_text).toBe(templateConfig.ai_policy_text);
});

test('instance details localizes populated workbench tabs and TOP SQL drawer', async ({ page }) => {
    const datasource = {
        id: 1, name: 'primary-db', host: '192.168.2.29', port: 5432, database: 'dbguard',
        db_type: 'postgresql', db_version: 'PostgreSQL 16.2', username: 'dbadmin',
        connection_status: 'normal', connection_checked_at: '2026-07-22T08:00:00Z',
        metric_source: 'system', tags: ['production'], remark: 'Primary database'
    };
    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/login') {
            return route.fulfill({ json: { user: {
                id: 1, username: 'admin', display_name: 'Admin', email: null, phone: null,
                locale: 'en-US', is_active: true, is_admin: true
            } } });
        }
        if (url.pathname === '/api/app/info') return route.fulfill({ json: { app_version: 'test' } });
        if (url.pathname === '/api/datasources') return route.fulfill({ json: [datasource] });
        if (url.pathname === '/api/instances/alert-summary') return route.fulfill({ json: { items: [] } });
        if (url.pathname === '/api/instances/1/summary') {
            return route.fulfill({ json: {
                datasource,
                health: { healthy: true, status: 'healthy', message: '', violations: [] },
                inspection: { next_scheduled_at: null }, metric_collected_at: '2026-07-22T08:05:00Z',
                active_alert_event_count: 1, active_alert_count: 2
            } });
        }
        if (url.pathname === '/api/inspections/config/1') {
            return route.fulfill({ json: {
                enabled: true, schedule_interval: 300, use_ai_analysis: true,
                next_scheduled_at: null, threshold_rules: { cpu_usage: 80 }
            } });
        }
        if (url.pathname === '/api/instances/1/variables') {
            return route.fulfill({ json: [{ key: 'max_connections', value: '200', category: 'connection' }] });
        }
        if (url.pathname === '/api/instances/1/sessions') {
            return route.fulfill({ json: [{
                session_id: '42', user: 'dbadmin', database: 'dbguard', client: '10.0.0.8',
                status: 'active', duration_seconds: 12, wait_event: 'ClientRead',
                sql_text: 'select 1', can_terminate: true
            }] });
        }
        if (url.pathname === '/api/datasources/1/top-sql') {
            return route.fulfill({ json: { data: [{
                sql_id: 'sql-1', sql_text: 'select * from orders', exec_count: 12,
                total_time_sec: 3.2, total_rows_scanned: 900, total_wait_time_sec: 0.4,
                avg_time_sec: 0.27, avg_rows_scanned: 75, avg_wait_time_sec: 0.03,
                last_exec_time: '2026-07-22T08:10:00Z'
            }] } });
        }
        if (url.pathname === '/api/datasources/1/explain-sql') {
            return route.fulfill({ json: { explain_result: { format: 'table', plan: [{ operation: 'Seq Scan' }] } } });
        }
        return route.fulfill({ json: [] });
    });

    await page.goto('/index.html#login');
    await page.locator('#login-username').fill('admin');
    await page.locator('#login-password').fill('password');
    await page.locator('#login-btn').click();
    await expect(page).toHaveURL(/#dashboard$/);

    await page.evaluate(() => Router.navigate('instance-detail?datasource=1&tab=config'));
    await expect(page).toHaveURL(/#instance-detail\?datasource=1&tab=config$/);
    await expect(page.locator('.instance-config-page')).toBeVisible();
    await expectNoChineseUi(page, '#page-content', 'instance details overview');

    await page.locator('[data-tab="parameters"]').click();
    await expect(page.locator('.instance-variables-table')).toBeVisible();
    await expectNoChineseUi(page, '#page-content', 'instance parameters');

    await page.locator('[data-tab="sessions"]').click();
    await expect(page.locator('.instance-sessions-table')).toBeVisible();
    await expectNoChineseUi(page, '#page-content', 'instance sessions');

    await page.locator('[data-tab="topSql"]').click();
    await expect(page.locator('.top-sql-table')).toBeVisible();
    await expectNoChineseUi(page, '#page-content', 'TOP SQL table');
    await page.locator('.top-sql-row').click();
    await expect(page.locator('#topSqlDrawer')).toHaveClass(/active/);
    await expectNoChineseUi(page, '#topSqlDrawer', 'TOP SQL drawer');
    await page.locator('#viewExplainPlan').click();
    await expect(page.locator('#explainPlanContent')).toContainText('Seq Scan');
    await expectNoChineseUi(page, '#topSqlDrawer', 'TOP SQL execution plan');
});

test('populated resource overview localizes dynamic labels and relative times', async ({ page }) => {
    const createdAt = new Date(Date.now() - 455 * 60 * 60 * 1000).toISOString();
    const datasources = [
        { id: 1, name: 'primary-db', host: '192.168.2.29', port: 5432, database: 'dbguard', db_type: 'postgresql', host_id: 1 },
        { id: 2, name: 'analytics-db', host: '192.168.2.30', port: 3306, database: 'analytics', db_type: 'mysql', host_id: 2 },
    ];
    const hosts = [
        { id: 1, name: 'db-host-1', host: '192.168.2.29', status: 'offline', status_message: '连接失败（超过5分钟未收到数据）' },
        { id: 2, name: 'db-host-2', host: '192.168.2.30', status: 'online', status_message: '' },
    ];

    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/login') {
            return route.fulfill({ json: { user: {
                id: 1, username: 'admin', display_name: 'Admin', email: null, phone: null,
                locale: 'en-US', is_active: true, is_admin: true
            } } });
        }
        if (url.pathname === '/api/app/info') return route.fulfill({ json: { app_version: 'test' } });
        if (url.pathname === '/api/datasources') return route.fulfill({ json: datasources });
        if (url.pathname === '/api/hosts') return route.fulfill({ json: hosts });
        if (url.pathname === '/api/alerts') {
            return route.fulfill({ json: { alerts: [{
                id: 10, datasource_id: 1, severity: 'critical', alert_type: 'system_error',
                metric_name: 'connection_status', title: '数据库连接失败', created_at: createdAt
            }], total: 1 } });
        }
        if (url.pathname === '/api/metrics/batch/dashboard') {
            return route.fulfill({ json: {
                '1': {
                    health: { status: 'error', message: '连接失败', violations: [{ type: 'connection_failure' }] },
                    metric: { data: { connections_active: 0, cpu_usage: 3.2 } }
                },
                '2': {
                    health: { status: 'healthy', message: '', violations: [] },
                    metric: { data: { connections_active: 4, cpu_usage: 12.5, qps: 8.4 } }
                }
            } });
        }
        return route.fulfill({ json: [] });
    });

    await page.goto('/index.html#login');
    await page.locator('#login-username').fill('admin');
    await page.locator('#login-password').fill('password');
    await page.locator('#login-btn').click();

    await expect(page.locator('#panel-hosts')).toContainText('Host health');
    await expect(page.locator('#panel-hosts')).toContainText('Online 1');
    await expect(page.locator('#panel-hosts')).toContainText('no data received for over 5 minutes');
    await expect(page.locator('#panel-dbs')).toContainText('Datasource health');
    await expect(page.locator('#panel-alerts')).toContainText('Active alerts');
    await expect(page.locator('#panel-alerts .alert-title')).toHaveText('Database connection failed');
    await expect(page.locator('#panel-alerts .alert-time')).toContainText('days ago');
    await expect(page.locator('#anomaly-grid')).toContainText('Connection failed');
    await expect(page.locator('#anomaly-grid')).toContainText('Active connections');
    await expect(page.locator('#last-update')).toContainText('Last updated');
    await expect(page.locator('#filter-health option').first()).toHaveText('All statuses');
    await expect(page.locator('#filter-search')).toHaveAttribute('placeholder', 'Search name/address...');

    await expectNoChineseUi(page, '#page-content', 'populated dashboard');
});

test('populated management pages localize interpolated counts and statuses', async ({ page }) => {
    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/login') {
            return route.fulfill({ json: { user: {
                id: 1, username: 'admin', display_name: 'Admin', email: null, phone: null,
                locale: 'en-US', is_active: true, is_admin: true
            } } });
        }
        if (url.pathname === '/api/app/info') return route.fulfill({ json: { app_version: 'test' } });
        if (url.pathname === '/api/users') {
            return route.fulfill({ json: [{
                id: 2, username: 'operator', display_name: 'Operator', email: 'operator@example.com', phone: null,
                is_admin: false, is_active: true, created_at: '2026-07-20T12:00:00Z'
            }] });
        }
        if (url.pathname === '/api/ai-models') {
            return route.fulfill({ json: [{
                id: 1, name: 'Primary model', provider: 'openai', protocol: 'openai', model_name: 'gpt-test',
                reasoning_effort: 'medium', context_window: 128000, base_url: 'https://api.example.com',
                api_key_masked: 'sk-***', is_default: true
            }] });
        }
        if (url.pathname === '/api/skills/categories') return route.fulfill({ json: { categories: ['通用诊断', '平台操作'] } });
        if (url.pathname === '/api/skills') {
            return route.fulfill({ json: [{
                id: 'health_check', name: 'Health check', description: 'Checks datasource health', category: '通用诊断',
                version: '1.0.0', tags: ['health'], permissions: ['read_datasource'], parameters: [], code: 'return {}',
                is_builtin: true, is_enabled: true
            }] });
        }
        return route.fulfill({ json: [] });
    });

    await page.goto('/index.html#login');
    await page.locator('#login-username').fill('admin');
    await page.locator('#login-password').fill('password');
    await page.locator('#login-btn').click();
    await expect(page.locator('#page-content')).toContainText('No datasources');

    await page.evaluate(() => Router.navigate('users'));
    await expect(page.locator('#page-content')).toContainText('1 users');
    await expect(page.locator('#page-content')).toContainText('Active');
    await expectNoChineseUi(page, '#page-content', 'users');

    await page.evaluate(() => Router.navigate('ai-models'));
    await expect(page.locator('#page-content')).toContainText('1 models configured');
    await expect(page.locator('#page-content')).toContainText('Reasoning strength: Medium');
    await expectNoChineseUi(page, '#page-content', 'ai-models');

    await page.evaluate(() => Router.navigate('skills'));
    await expect(page.locator('#page-content')).toContainText('Built-in');
    await expect(page.locator('#page-content')).toContainText('View');
    await expect(page.locator('#page-content')).toContainText('General Diagnostics');
    await expect(page.locator('#category-filter')).toContainText('Platform Operations');
    await expectNoChineseUi(page, '#page-content', 'skills');

    await page.evaluate(() => {
        DiagnosisPage.skillAuthorizationCatalog = {
            groups: [{
                id: 'platform_operations', label: '平台操作',
                description: '允许 AI 调用平台操作类 skill。', warning_level: 'medium', enabled_by_default: false,
                items: [{ id: 'list_documents', kind: 'tool', description: '浏览内置诊断文档目录。' }]
            }]
        };
        DiagnosisPage.skillAuthorizations = null;
        DiagnosisPage._showSkillAuthorizationModal();
    });
    await expect(page.locator('#modal-container')).toContainText('Skill Authorization');
    await expect(page.locator('#modal-container')).toContainText('Platform Operations');
    await expect(page.locator('#modal-container')).toContainText('Built-in list_documents');
    await expectNoChineseUi(page, '#modal-container', 'skill authorization');
    await page.evaluate(() => Modal.hide());

    await page.evaluate(async () => {
        I18n.setLocale('zh-CN', { persist: false });
        await Router.refreshCurrentRoute();
    });
    await expect(page.locator('#page-content')).toContainText('内置');
    await expect(page.locator('#page-content')).toContainText('查看');
    await page.evaluate(() => SkillsPage.createSkill());
    await expect(page.locator('#modal-container')).toContainText('新建技能');
    await expect(page.locator('#modal-container')).toContainText('仅支持小写字母、数字和下划线');
});

test('create and edit dialogs render without Chinese UI text in English mode', async ({ page }) => {
    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/login') {
            return route.fulfill({ json: { user: {
                id: 1, username: 'admin', display_name: 'Admin', email: null, phone: null,
                locale: 'en-US', is_active: true, is_admin: true
            } } });
        }
        if (url.pathname === '/api/app/info') return route.fulfill({ json: { app_version: 'test' } });
        return route.fulfill({ json: [] });
    });
    await page.goto('/index.html#login');
    await page.locator('#login-username').fill('admin');
    await page.locator('#login-password').fill('password');
    await page.locator('#login-btn').click();
    await expect.poll(() => page.evaluate(() => I18n.t('datasourceForm.namePlaceholder'))).toBe('My database');
    expect(await page.evaluate(() => DatasourceForm.show.toString())).toContain('datasourceForm.namePlaceholder');

    await page.evaluate(() => new Promise(resolve => {
        const host = document.createElement('div');
        host.id = 'i18n-datasource-selector';
        document.body.appendChild(host);
        const getDatasources = API.getDatasources;
        API.getDatasources = async () => [{
            id: 1, name: 'primary-db', db_type: 'postgresql', host: '192.168.2.29', port: 5432,
            connection_status: 'healthy'
        }];
        new DatasourceSelector({
            container: host,
            onLoad: () => {
                API.getDatasources = getDatasources;
                resolve();
            }
        });
    }));
    await page.locator('#i18n-datasource-selector .datasource-selector-button').evaluate(button => button.click());
    await expectNoChineseUi(page, '#i18n-datasource-selector', 'datasource selector');
    await page.locator('#i18n-datasource-selector').evaluate(element => element.remove());

    const dialogs = [
        'Sidebar._showProfileModal()',
        'Sidebar._showChangePasswordModal()',
        'Sidebar._logout()',
        'DatasourceForm.show(null)',
        'HostsPage._showForm(null)',
        'SystemConfigsPage.showAddModal()',
        'AlertTemplatesPage._showForm(null)',
        "Object.assign(DocumentsPage, { currentCategory: { id: 1 } }); DocumentsPage.newDocument()",
        'AIModelsPage._showForm(null)',
        'UsersPage._showCreateModal()',
        "UsersPage._showResetPasswordModal({ id: 2, username: 'operator' })",
        "UsersPage._showLoginLogs({ id: 2, username: 'operator' })",
        'ScheduledTasksPage.showTaskModal()',
        'integrationsPage.showCreateIntegrationModal()',
        'SkillsPage.createSkill()',
    ];
    for (const expression of dialogs) {
        await page.evaluate(async value => { await eval(value); }, expression);
        await expect(page.locator('#modal-container')).toBeVisible();
        await page.waitForTimeout(30);
        await expectNoChineseUi(page, '#modal-container', expression);
        await page.evaluate(() => Modal.hide());
    }
});

test('integration management localizes built-in metadata and every dialog', async ({ page }) => {
    const integrations = [
        {
            id: 1, integration_id: 'builtin_feishu_webhook', name: '飞书 Webhook 通知',
            description: '通过飞书 Webhook 发送交互式卡片通知', integration_type: 'outbound_notification',
            category: 'im', enabled: true, is_builtin: true, code: 'async def send_notification(): return True',
            config_schema: { properties: { webhook_url: { title: 'Webhook URL', description: '飞书机器人 Webhook 地址' } }, required: ['webhook_url'] }
        },
        {
            id: 2, integration_id: 'builtin_aliyun_rds', name: '阿里云 RDS 监控数据采集',
            description: '从阿里云 RDS API 采集监控指标', integration_type: 'inbound_metric',
            category: 'monitoring', enabled: true, is_builtin: true, code: 'async def fetch_metrics(): return {}',
            config_schema: { properties: { region_id: { title: '地域 ID', description: '阿里云地域 ID，如 cn-hangzhou', default: 'cn-hangzhou' } }, required: ['region_id'] }
        },
        {
            id: 3, integration_id: 'builtin_weixin_bot', name: '微信机器人对话',
            description: '微信机器人入站对话配置', integration_type: 'bot', category: 'im',
            enabled: true, is_builtin: true, code: 'async def handle_event(): return True',
            config_schema: { properties: {}, required: [] }
        },
        {
            id: 4, integration_id: 'builtin_feishu_bot', name: '飞书机器人对话',
            description: '飞书机器人入站对话配置', integration_type: 'bot', category: 'im',
            enabled: true, is_builtin: true, code: 'APP_ID = ""', config_schema: { properties: {}, required: [] }
        },
        {
            id: 5, integration_id: 'legacy_wecom_webhook', name: '企业微信',
            description: '通过企业微信 Webhook 发送告警和事件通知', integration_type: 'outbound_notification',
            category: 'im', enabled: true, is_builtin: true, code: 'async def send_notification(): return True',
            config_schema: { properties: {}, required: [] }
        },
        {
            id: 6, integration_id: 'builtin_wecom_bot', name: '企业微信机器人',
            description: '企业微信机器人入站对话配置', integration_type: 'bot', category: 'im',
            enabled: true, is_builtin: true, code: 'async def handle_event(): return True',
            config_schema: { properties: {}, required: [] }
        }
    ];

    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/login') {
            return route.fulfill({ json: { user: {
                id: 1, username: 'admin', display_name: 'Admin', email: null, phone: null,
                locale: 'en-US', is_active: true, is_admin: true
            } } });
        }
        if (url.pathname === '/api/app/info') return route.fulfill({ json: { app_version: 'test' } });
        if (url.pathname === '/api/integrations') return route.fulfill({ json: integrations });
        if (url.pathname === '/api/integration-bots') {
            return route.fulfill({ json: [
                { code: 'weixin_bot', name: '微信机器人', enabled: true, params: { login_status: 'confirmed' } },
                { code: 'wecom_bot', name: '企业微信', enabled: true, params: { login_status: 'confirmed' } }
            ] });
        }
        if (url.pathname === '/api/datasources') {
            return route.fulfill({ json: [{ id: 1, name: 'primary-db', db_type: 'mysql' }] });
        }
        return route.fulfill({ json: [] });
    });

    await page.goto('/index.html#login');
    await page.locator('#login-username').fill('admin');
    await page.locator('#login-password').fill('password');
    await page.locator('#login-btn').click();
    await expect(page).toHaveURL(/#dashboard$/);
    await expect(page.locator('#last-update')).toContainText('Last updated');
    await page.evaluate(() => Router.navigate('integrations'));
    await expect(page).toHaveURL(/#integrations$/);
    await expect(page.locator('.integration-card')).toHaveCount(6);
    await expect(page.locator('#page-content')).toContainText('Alibaba Cloud RDS Metrics');
    await expect(page.locator('#page-content')).toContainText('Weixin Bot Conversation');
    await expect(page.locator('#page-content')).toContainText('WeCom Webhook Notification');
    await expect(page.locator('#page-content')).toContainText('WeCom Bot Conversation');
    await expectNoChineseUi(page, '#page-content', 'populated integrations');

    await page.evaluate(() => integrationsPage.viewIntegration(1));
    await expect(page.locator('#modal-container')).toContainText('Feishu Webhook Notification');
    await expectNoChineseUi(page, '#modal-container', 'integration details');
    await page.evaluate(() => Modal.hide());

    await page.evaluate(() => integrationsPage.testIntegration(2));
    await expect(page.locator('#modal-container')).toContainText('Test Alibaba Cloud RDS Metrics');
    await expect(page.locator('#test-param-region_id')).toHaveAttribute('placeholder', 'Alibaba Cloud region ID, such as cn-hangzhou');
    await expectNoChineseUi(page, '#modal-container', 'integration test');
    await page.evaluate(() => Modal.hide());

    await page.evaluate(() => integrationsPage.editIntegration(4));
    await expect(page.locator('#modal-container')).toContainText('Feishu uses long-connection mode by default');
    await expectNoChineseUi(page, '#modal-container', 'integration editor');
    await page.evaluate(() => Modal.hide());

    await page.evaluate(() => integrationsPage._showWeixinLoginModal({ params: { login_status: 'confirmed' } }));
    await expect(page.locator('#modal-container')).toContainText('Weixin Bot Is Ready');
    await expectNoChineseUi(page, '#modal-container', 'Weixin bot configuration');
});

test('host details localize populated info, monitor, and process views', async ({ page }) => {
    const host = {
        id: 1, name: 'db-host-1', host: '192.168.2.29', port: 22,
        username: 'operator', status: 'normal'
    };
    const metric = {
        collected_at: '2026-07-21T08:00:00Z', cpu_usage: 12.5, memory_usage: 42.5, disk_usage: 37.5,
        data: {
            memory_total_bytes: 8589934592, memory_used_bytes: 3650722201,
            disk_total_bytes: 107374182400, disk_used_bytes: 40265318400,
            load_avg_1min: 0.25, disk_read_iops: 10, disk_write_iops: 5,
            disk_read_kb_per_sec: 20, disk_write_kb_per_sec: 10,
            network_rx_kb_per_sec: 30, network_tx_kb_per_sec: 15
        }
    };

    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/login') {
            return route.fulfill({ json: { user: {
                id: 1, username: 'admin', display_name: 'Admin', email: null, phone: null,
                locale: 'en-US', is_active: true, is_admin: true
            } } });
        }
        if (url.pathname === '/api/app/info') return route.fulfill({ json: { app_version: 'test' } });
        if (url.pathname === '/api/hosts') return route.fulfill({ json: [host] });
        if (url.pathname === '/api/host-detail/1/config') {
            return route.fulfill({ json: {
                collected_at: '2026-07-21T08:00:00Z',
                system: {
                    hostname: 'db-host-1', os_name: 'Linux', os_version: 'Test OS', kernel: '6.0',
                    uptime_seconds: 93784, load_avg_1: 0.25, load_avg_5: 0.2, load_avg_15: 0.1
                },
                cpu: { model: 'Test CPU', physical_cpus: 1, cores: 2, mhz: 2400 },
                memory: {
                    MemTotal: '8388608 kB', MemFree: '4194304 kB', MemAvailable: '5242880 kB',
                    Buffers: '131072 kB', Cached: '1048576 kB', SwapTotal: '0 kB', SwapFree: '0 kB'
                },
                disk: [{
                    filesystem: '/dev/test', mounted_on: '/', size: '100G', used: '40G',
                    available: '60G', use_percent: '40%'
                }],
                network: [{ interface: 'eth0', family: 'IPv4', address: '192.168.2.29' }]
            } });
        }
        if (url.pathname === '/api/host-detail/1/summary') {
            return route.fulfill({ json: { host, latest_metric: metric, uptime_seconds: 93784 } });
        }
        if (url.pathname === '/api/host-detail/1/metrics') return route.fulfill({ json: [metric] });
        if (url.pathname === '/api/host-detail/1/network-topology') {
            return route.fulfill({ json: {
                host, stats: { total_connections: 3, established: 2, time_wait: 1, listen: 0 },
                connections: [{
                    remote_ip: '10.0.0.8', connection_count: 3,
                    states: { ESTABLISHED: 2, TIME_WAIT: 1 }
                }]
            } });
        }
        if (url.pathname === '/api/hosts/1/processes') {
            return route.fulfill({ json: [{
                pid: 42, user: 'postgres', cpu_percent: 2.5, memory_percent: 1.5,
                state: 'running', command: 'postgres'
            }] });
        }
        if (url.pathname === '/api/hosts/1/processes/42') {
            return route.fulfill({ json: {
                pid: 42, user: 'postgres', state: 'running', start_time: '08:00',
                cpu_percent: 2.5, memory_percent: 1.5, vsz: 1024, rss: 512,
                cpu_time: '00:01', cwd: '/var/lib/postgresql', command: 'postgres',
                cmdline: 'postgres --config=test', io: {}, network_connections: [], environment: {}
            } });
        }
        return route.fulfill({ json: [] });
    });

    await page.goto('/index.html#login');
    await page.locator('#login-username').fill('admin');
    await page.locator('#login-password').fill('password');
    await page.locator('#login-btn').click();
    await expect(page).toHaveURL(/#dashboard$/);

    const tabReadySelector = {
        info: '.host-config-page',
        monitor: '.host-monitor-page',
        processes: '#process-table-body .process-row',
        network: '.host-network-page',
        terminal: '.host-terminal-container'
    };
    const assertLocalizedTab = async tab => {
        await page.evaluate(value => Router.navigate(`host-detail?host=1&tab=${value}`), tab);
        await expect(page).toHaveURL(new RegExp(`host-detail\\?host=1&tab=${tab}$`));
        await expect(page.locator(tabReadySelector[tab])).toBeVisible();
        await expectNoChineseUi(page, '#page-content', `host detail ${tab}`);
    };
    for (const tab of ['info', 'monitor', 'processes']) {
        await assertLocalizedTab(tab);
    }

    await page.locator('.process-row').click();
    await expect(page.locator('#process-detail-drawer')).toHaveClass(/open/);
    await expect(page.locator('#process-detail-content')).toContainText('Command Details');
    await expectNoChineseUi(page, '#process-detail-content', 'process details');

    await assertLocalizedTab('network');
    await page.locator('.host-network-list-item').click();
    await expect(page.locator('#modal-container')).toContainText('Network Node Details');
    await expectNoChineseUi(page, '#modal-container', 'network node details');
    await page.evaluate(() => Modal.hide());

    await assertLocalizedTab('terminal');
});
