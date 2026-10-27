const { test, expect } = require('@playwright/test');

test.use({ timezoneId: 'Asia/Shanghai' });

const pageErrors = new WeakMap();
test.beforeEach(({ page }) => {
    const errors = [];
    pageErrors.set(page, errors);
    page.on('pageerror', error => errors.push(error.message));
});
test.afterEach(({ page }) => {
    expect(pageErrors.get(page), 'No uncaught browser exceptions').toEqual([]);
});

function metric(qps = 150.5, ago = 120000, datasourceId = 2) {
    return {
        datasource_id: datasourceId, metric_type: 'db_status',
        collected_at: new Date(Date.now() - ago).toISOString(),
        data: {
            connections_active: 2, connections_total: 1341, max_connections: 8000,
            qps, tps: 4.87, cache_hit_rate: 100, uptime: 19765421,
            network_rx_rate: 36525.3, network_tx_rate: 860042.21,
        },
    };
}

async function setup(page, options = {}) {
    const state = {
        history: [metric()], latest: null, historyRequests: [], refreshes: 0,
        sockets: [], ...options,
    };
    const datasources = [2, 3].map(id => ({
        id, name: `mysql-${id}`, db_type: 'mysql', host: '127.0.0.1', port: 3306,
        connection_status: 'connected', is_active: true,
    }));
    await page.routeWebSocket('**/ws/monitor/**', ws => state.sockets.push(ws));
    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        if (path === '/api/datasources') return route.fulfill({ json: datasources });
        if (path === '/api/instances/alert-summary') return route.fulfill({ json: { items: [] } });
        if (/\/api\/instances\/\d+\/summary$/.test(path)) {
            const id = Number(path.split('/')[3]);
            return route.fulfill({ json: { datasource: datasources.find(ds => ds.id === id) } });
        }
        if (/\/api\/metrics\/\d+\/health$/.test(path)) {
            return route.fulfill({ json: { status: 'healthy', healthy: true, message: 'OK', violations: [] } });
        }
        if (/\/api\/metrics\/\d+\/refresh$/.test(path)) {
            state.refreshes++;
            if (state.refreshError) return route.fulfill({ status: 503, json: { detail: state.refreshError } });
            if (state.onRefresh) await state.onRefresh();
            return route.fulfill({ json: { success: true } });
        }
        if (/\/api\/metrics\/\d+\/latest$/.test(path)) {
            if (state.latestHandler) return state.latestHandler(route);
            if (state.latestError) return route.fulfill({ status: 503, json: { detail: state.latestError } });
            return route.fulfill({ json: state.latest || state.history[0] || null });
        }
        if (/\/api\/metrics\/\d+$/.test(path)) {
            state.historyRequests.push(url);
            if (state.historyHandler) return state.historyHandler(route);
            if (state.historyError) return route.fulfill({ status: 503, json: { detail: state.historyError } });
            return route.fulfill({ json: state.history });
        }
        return route.fulfill({ json: [] });
    });
    await page.goto('/index.html#login');
    await page.waitForFunction(() => typeof MonitorPage !== 'undefined');
    await page.evaluate(locale => {
        I18n.setLocale(locale, { persist: false });
        Store.set('currentUser', { id: 1, username: 'test', locale, is_admin: true });
        Router.navigate('instance-detail?datasource=2&tab=monitor');
    }, options.locale || 'zh-CN');
    await expect(page.locator('#monitor-charts')).toBeVisible();
    return state;
}

async function qpsValues(page) {
    return page.evaluate(() => [...(ChartPanel.charts.qps?.data.datasets[0].data || [])]);
}

test('initial load and manual refresh update real charts and cards, including zero values', async ({ page }) => {
    const state = await setup(page);
    await expect.poll(() => qpsValues(page)).toEqual([150.5]);
    await expect(page.locator('#chart-value-connections')).toHaveText('2 / 1,341');
    await expect(page.locator('#chart-value-cache_hit')).toHaveText('100');
    await expect(page.locator('#chart-value-tps')).toHaveText('4.87');
    await expect(page.locator('#monitor-status')).toBeHidden();
    expect(await page.evaluate(() => ChartPanel.charts.qps.width)).toBeGreaterThan(0);

    state.onRefresh = async () => {
        state.history = [metric(0, 60000), ...state.history];
    };
    await page.locator('#refresh-btn').click();
    await expect.poll(() => qpsValues(page)).toEqual([150.5, 0]);
    await expect(page.locator('#monitor-metrics .metric-card').nth(1)).toContainText('0');
    await expect(page.locator('#refresh-btn')).toBeEnabled();
    expect(state.refreshes).toBe(1);
    expect(state.historyRequests).toHaveLength(2);
    await expect(page.locator('#monitor-status')).toBeHidden();
});

test('history and latest failures remain visible independently and retry recovers safely', async ({ page }) => {
    const state = await setup(page);
    await expect.poll(() => qpsValues(page)).toEqual([150.5]);
    state.historyError = '<img src=x onerror="window.injected=true">';
    state.latestError = 'latest unavailable';
    await page.locator('#refresh-btn').click();
    await expect(page.locator('#monitor-status')).toContainText('历史指标加载失败');
    await expect(page.locator('#monitor-status')).toContainText('最新指标加载失败');
    await expect(page.locator('#monitor-status')).toHaveCSS('border-top-width', '1px');
    await expect(page.locator('#monitor-status img')).toHaveCount(0);
    expect(await qpsValues(page)).toEqual([150.5]);
    await expect(page.locator('#refresh-btn')).toBeEnabled();

    state.latestError = null;
    state.historyError = null;
    state.history = [metric(230.86, 60000)];
    await page.getByRole('button', { name: '重试', exact: true }).click();
    await expect.poll(() => qpsValues(page)).toEqual([230.86]);
    await expect(page.locator('#monitor-status')).toBeHidden();
});

test('failed collection shows an inline error and retry actually collects again', async ({ page }) => {
    const state = await setup(page);
    await expect.poll(() => qpsValues(page)).toEqual([150.5]);
    state.refreshError = 'collection unavailable';
    await page.locator('#refresh-btn').click();
    await expect(page.locator('#monitor-status')).toContainText('刷新失败: collection unavailable');
    expect(await qpsValues(page)).toEqual([150.5]);
    await expect(page.locator('#refresh-btn')).toBeEnabled();
    state.refreshError = null;
    state.onRefresh = async () => { state.history = [metric(231, 60000)]; };
    await page.getByRole('button', { name: '重试', exact: true }).click();
    await expect.poll(() => qpsValues(page)).toEqual([231]);
    expect(state.refreshes).toBe(2);
    await expect(page.locator('#monitor-status')).toBeHidden();
});

test('empty history shows an explicit state and clears curves from a previous range', async ({ page }) => {
    const state = await setup(page, { history: [] });
    await expect(page.locator('#monitor-status')).toContainText('所选时间范围');
    expect(await qpsValues(page)).toEqual([]);
    state.history = [metric(230.86)];
    await page.getByRole('button', { name: '重试', exact: true }).click();
    await expect.poll(() => qpsValues(page)).toEqual([230.86]);
    state.history = [];
    await page.locator('#refresh-btn').click();
    await expect.poll(() => qpsValues(page)).toEqual([]);
    await expect(page.locator('#chart-value-qps')).toHaveText('--');
    await expect(page.locator('#monitor-status')).toContainText('所选时间范围');
});

test('missing Chart.js shows an actionable error and retry reinitializes charts', async ({ page }) => {
    await page.route('**/lib/chart.js/dist/chart.umd.js', route => route.abort());
    await setup(page);
    await expect(page.locator('#monitor-status')).toContainText('图表加载失败');
    await expect(page.locator('#monitor-metrics .metric-card').nth(1)).toContainText('150.5');
    await page.unroute('**/lib/chart.js/dist/chart.umd.js');
    // Load the UMD resource in the same global mode used by index.html, before Monaco.
    await page.evaluate(() => { window.savedDefine = window.define; window.define = undefined; });
    await page.addScriptTag({ url: '/lib/chart.js/dist/chart.umd.js' });
    await page.evaluate(() => { window.define = window.savedDefine; });
    await page.getByRole('button', { name: '重试', exact: true }).click();
    await expect.poll(() => qpsValues(page)).toEqual([150.5]);
    await expect(page.locator('#monitor-status')).toBeHidden();
});

test('a partial chart initialization failure is reported and retry replaces destroyed instances', async ({ page }) => {
    await setup(page);
    await expect.poll(() => qpsValues(page)).toEqual([150.5]);
    await page.evaluate(() => {
        window.realChart = Chart;
        window.Chart = new Proxy(Chart, {
            construct(target, args) {
                const chart = Reflect.construct(target, args);
                if (args[0].id === 'chart-qps') throw new Error('canvas failure after registration');
                return chart;
            },
        });
        MonitorPage._initCharts();
    });
    await expect(page.locator('#monitor-status')).toContainText('图表加载失败');
    expect(await page.evaluate(() => 'qps' in ChartPanel.charts)).toBe(false);
    expect(await page.evaluate(() => Boolean(Chart.getChart('chart-qps')))).toBe(false);
    await page.evaluate(() => { window.Chart = window.realChart; });
    await page.getByRole('button', { name: '重试', exact: true }).click();
    await expect.poll(() => qpsValues(page)).toEqual([150.5]);
    await expect(page.locator('#monitor-status')).toBeHidden();
});

test('refresh merges WebSocket packets received during the history query without duplicates or rollback', async ({ page }) => {
    const state = await setup(page);
    await expect.poll(() => qpsValues(page)).toEqual([150.5]);
    await expect.poll(() => state.sockets.length).toBe(1);
    let release;
    state.historyHandler = route => new Promise(resolve => {
        release = async () => { await route.fulfill({ json: state.history }); resolve(); };
    });
    await page.locator('#refresh-btn').click();
    await expect.poll(() => Boolean(release)).toBe(true);
    const live = { ...metric(240, 30000), type: 'db_status' };
    state.sockets[0].send(JSON.stringify(live));
    state.sockets[0].send(JSON.stringify(live));
    await expect.poll(() => qpsValues(page)).toEqual([150.5, 240]);
    await release();
    await expect(page.locator('#refresh-btn')).toBeEnabled();
    expect(await qpsValues(page)).toEqual([150.5, 240]);
    await expect(page.locator('#monitor-metrics .metric-card').nth(1)).toContainText('240');
    state.sockets[0].send(JSON.stringify(live));
    await expect(page.locator('#chart-value-qps')).toHaveText('240');
    expect(await qpsValues(page)).toEqual([150.5, 240]);
});

test('a slow response from the previous instance cannot replace current charts', async ({ page }) => {
    const state = await setup(page);
    await expect.poll(() => qpsValues(page)).toEqual([150.5]);
    let release;
    state.historyHandler = route => {
        if (new URL(route.request().url()).pathname === '/api/metrics/2') {
            return new Promise(resolve => {
                release = async () => { await route.fulfill({ json: [metric(999)] }); resolve(); };
            });
        }
        return route.fulfill({ json: [metric(42, 60000, 3)] });
    };
    await page.locator('#refresh-btn').click();
    await expect.poll(() => Boolean(release)).toBe(true);
    await page.evaluate(() => Router.navigate('instance-detail?datasource=3&tab=monitor'));
    await expect.poll(() => qpsValues(page)).toEqual([42]);
    await release();
    await expect(page.locator('#chart-value-qps')).toHaveText('42');
    expect(await qpsValues(page)).toEqual([42]);
});

test('UTC-naive history stays within the selected range in Shanghai time', async ({ page }) => {
    const sample = metric();
    sample.collected_at = sample.collected_at.replace('Z', '');
    await setup(page, { history: [sample] });
    await expect.poll(() => qpsValues(page)).toEqual([150.5]);
    await expect(page.locator('#monitor-status')).toBeHidden();
});

test('English error and empty states are localized and recover', async ({ page }) => {
    const state = await setup(page, { locale: 'en-US', historyError: 'unavailable' });
    await expect(page.locator('#monitor-status')).toContainText('Failed to load metric history');
    state.historyError = null;
    state.history = [];
    await page.getByRole('button', { name: 'Retry', exact: true }).click();
    await expect(page.locator('#monitor-status')).toContainText('There is no data in the selected time range');
    expect(await page.locator('#monitor-status').innerText()).not.toMatch(/[\p{Script=Han}]/u);
});

test('manual refresh preserves a custom historical range and resuming returns to live data', async ({ page }) => {
    const state = await setup(page);
    await expect.poll(() => qpsValues(page)).toEqual([150.5]);
    const start = new Date(Date.now() - 180000).toISOString();
    const end = new Date(Date.now() - 90000).toISOString();
    await page.evaluate(async ({ start, end }) => {
        await MonitorPage._loadCustomRange(2, start, end);
    }, { start, end });
    state.history = [metric(0)];
    await page.locator('#refresh-btn').click();
    await expect.poll(() => qpsValues(page)).toEqual([0]);
    const query = state.historyRequests.at(-1).searchParams;
    expect(query.get('start_time')).toBe(start);
    expect(query.get('end_time')).toBe(end);
    expect(query.has('minutes')).toBe(false);

    await page.locator('#realtime-toggle').click();
    await expect.poll(() => state.historyRequests.at(-1).searchParams.get('minutes')).toBe('60');
    await expect(page.locator('#time-range-select')).toHaveValue('60');
});

test('WebSocket failure is visible and manual refresh still updates charts', async ({ page }) => {
    const state = await setup(page);
    await expect.poll(() => qpsValues(page)).toEqual([150.5]);
    await expect.poll(() => state.sockets.length).toBe(1);
    state.sockets[0].close();
    await expect(page.locator('#monitor-status')).toContainText('实时监控连接已断开');
    state.history = [metric(260, 60000)];
    await page.locator('#refresh-btn').click();
    await expect.poll(() => qpsValues(page)).toEqual([260]);
});
