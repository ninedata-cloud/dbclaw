const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
    testDir: './tests/e2e',
    timeout: 30_000,
    use: { baseURL: 'http://127.0.0.1:4173', headless: true },
    webServer: {
        command: 'python3 -m http.server 4173 --directory frontend',
        url: 'http://127.0.0.1:4173/index.html',
        reuseExistingServer: true,
    },
});
