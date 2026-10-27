const { test, expect } = require('@playwright/test');

for (const scenario of [
    { name: 'configured interval', value: 30, seconds: 30 },
    { name: 'invalid setting falls back to 15 seconds', value: 0, seconds: 15 },
    { name: 'unavailable settings fall back to 15 seconds', fail: true, seconds: 15 },
]) {
    test(`dashboard auto-refresh: ${scenario.name}`, async ({ page }) => {
        let refreshes = 0;
        let configuredInterval = scenario.value;
        await page.clock.install();
        await page.route('**/api/**', async route => {
            const url = new URL(route.request().url());
            if (url.pathname === '/api/auth/login') {
                return route.fulfill({ json: { user: {
                    id: 2, username: 'user', display_name: 'User',
                    locale: 'zh-CN', is_active: true, is_admin: false,
                } } });
            }
            if (url.pathname === '/api/system-configs/dashboard') {
                if (scenario.fail) return route.fulfill({ status: 503, json: {} });
                return route.fulfill({ json: { refresh_interval_seconds: configuredInterval } });
            }
            if (url.pathname === '/api/datasources') {
                return route.fulfill({ json: [{ id: 1, name: 'db', db_type: 'mysql' }] });
            }
            if (url.pathname === '/api/alerts') {
                return route.fulfill({ json: { alerts: [], total: 0 } });
            }
            if (url.pathname === '/api/metrics/batch/dashboard') {
                refreshes += 1;
                return route.fulfill({ json: {} });
            }
            return route.fulfill({ json: [] });
        });

        await page.goto('/index.html#login');
        await page.locator('#login-username').fill('user');
        await page.locator('#login-password').fill('password');
        await page.locator('#login-btn').click();
        await expect.poll(() => refreshes).toBe(1);
        await page.waitForFunction(() => DashboardPage._timer !== null);

        await page.clock.fastForward(scenario.seconds * 1000 - 1);
        expect(refreshes).toBe(1);
        await page.clock.fastForward(1);
        await expect.poll(() => refreshes).toBe(2);

        // Reopening the dashboard reads the new setting and replaces the old timer.
        if (!scenario.fail && scenario.value === 30) {
            await page.evaluate(() => Router.navigate('hosts'));
            await page.clock.fastForward(30000);
            expect(refreshes).toBe(2);
            configuredInterval = 5;
            await page.evaluate(() => Router.navigate('dashboard'));
            await expect.poll(() => refreshes).toBe(3);
            await page.waitForFunction(() => DashboardPage._timer !== null);
            await page.clock.fastForward(5000);
            await expect.poll(() => refreshes).toBe(4);
        }
    });
}
