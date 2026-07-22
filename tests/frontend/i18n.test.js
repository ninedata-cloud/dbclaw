const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');
const test = require('node:test');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '../..');
const storage = new Map();
const domReadyListeners = [];

global.window = global;
global.localStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
};
global.document = {
    body: null,
    title: '',
    documentElement: { lang: '' },
    querySelector: () => null,
    addEventListener: (name, listener) => { if (name === 'DOMContentLoaded') domReadyListeners.push(listener); },
    dispatchEvent: () => true,
};
global.CustomEvent = class CustomEvent { constructor(name, options) { this.type = name; this.detail = options?.detail; } };
global.Node = { ELEMENT_NODE: 1, TEXT_NODE: 3 };
global.NodeFilter = { SHOW_ELEMENT: 1, SHOW_TEXT: 4 };
global.confirm = () => true;

for (const file of [
    'frontend/js/locales/zh-CN.js',
    'frontend/js/locales/en-US.js',
    'frontend/js/locales/page-copy-zh-CN.js',
    'frontend/js/locales/page-copy-en-US.js',
    'frontend/js/i18n.js'
]) {
    vm.runInThisContext(fs.readFileSync(path.join(root, file), 'utf8'), { filename: file });
}

const inspectionPage = vm.runInThisContext(
    `${fs.readFileSync(path.join(root, 'frontend/js/pages/inspection.js'), 'utf8')}\nInspectionPage;`,
    { filename: 'frontend/js/pages/inspection.js' }
);
const alertsPage = vm.runInThisContext(
    `${fs.readFileSync(path.join(root, 'frontend/js/pages/alerts.js'), 'utf8')}\nAlertsPage;`,
    { filename: 'frontend/js/pages/alerts.js' }
);
const dashboardPage = vm.runInThisContext(
    `${fs.readFileSync(path.join(root, 'frontend/js/pages/dashboard.js'), 'utf8')}\nDashboardPage;`,
    { filename: 'frontend/js/pages/dashboard.js' }
);

function flattenKeys(value, prefix = '') {
    return Object.entries(value).flatMap(([key, child]) => {
        const full = prefix ? `${prefix}.${key}` : key;
        if (child && typeof child === 'object') return flattenKeys(child, full);
        return [full];
    });
}

function flattenEntries(value, prefix = '') {
    return Object.entries(value).flatMap(([key, child]) => {
        const full = prefix ? `${prefix}.${key}` : key;
        if (child && typeof child === 'object') return flattenEntries(child, full);
        return [[full, String(child)]];
    });
}

function placeholders(value) {
    return [...value.matchAll(/\{([A-Za-z0-9_]+)\}/g)].map(match => match[1]).sort();
}

test('locale catalogs have identical key sets', () => {
    const zh = flattenKeys(DBClawLocales['zh-CN']).sort();
    const en = flattenKeys(DBClawLocales['en-US']).sort();
    assert.deepEqual(en, zh);
});

test('locale catalogs have identical interpolation placeholders', () => {
    const zh = new Map(flattenEntries(DBClawLocales['zh-CN']));
    const en = new Map(flattenEntries(DBClawLocales['en-US']));
    for (const [key, value] of zh) {
        assert.deepEqual(placeholders(en.get(key)), placeholders(value), key);
    }
});

test('page copy uses semantic keys rather than generated placeholders', () => {
    const generated = /^(?:value|message|localizedContent)(?:Value|\d)*|^valueValue/;
    for (const [namespace, entries] of Object.entries(DBClawLocales['en-US'].pageCopy)) {
        for (const key of Object.keys(entries)) {
            assert.equal(generated.test(key), false, `pageCopy.${namespace}.${key}`);
        }
    }
});

test('every static translation reference exists in the locale catalog', () => {
    const files = [];
    const collect = directory => {
        for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
            if (entry.name === 'locales' || entry.name === 'lib') continue;
            const filename = path.join(directory, entry.name);
            if (entry.isDirectory()) collect(filename);
            else if (entry.name.endsWith('.js')) files.push(filename);
        }
    };
    const hasKey = key => key.split('.').every((part, index, parts) => {
        let value = DBClawLocales['en-US'];
        for (const segment of parts.slice(0, index + 1)) {
            if (!value || !Object.prototype.hasOwnProperty.call(value, segment)) return false;
            value = value[segment];
        }
        return true;
    });

    collect(path.join(root, 'frontend/js'));
    const missing = [];
    for (const filename of files) {
        const source = fs.readFileSync(filename, 'utf8');
        for (const match of source.matchAll(/I18n\.t\(\s*(['"])([^'"]+)\1/g)) {
            if (!hasKey(match[2])) {
                const line = source.slice(0, match.index).split('\n').length;
                missing.push(`${path.relative(root, filename)}:${line}: ${match[2]}`);
            }
        }
    }
    assert.deepEqual(missing, []);
});

test('English catalog values do not contain Han characters except the Chinese language label', () => {
    function visit(value, key = '') {
        if (value && typeof value === 'object') {
            for (const [childKey, child] of Object.entries(value)) visit(child, `${key}.${childKey}`);
            return;
        }
        if (key === '.common.chinese') return;
        assert.equal(/[\p{Script=Han}]/u.test(String(value)), false, `${key}: ${value}`);
    }
    visit(DBClawLocales['en-US']);
});

test('all first-party JavaScript UI copy uses explicit locale keys', () => {
    const output = execFileSync(process.execPath, [path.join(root, 'scripts/i18n-frontend-audit.js'), '--strict'], {
        cwd: root,
        encoding: 'utf8',
    });
    assert.match(output, /0 violations/);
});

test('placeholder literals do not bypass the locale catalogs', () => {
    const files = [];
    const collect = directory => {
        for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
            if (entry.name === 'locales' || entry.name === 'lib') continue;
            const filename = path.join(directory, entry.name);
            if (entry.isDirectory()) collect(filename);
            else if (/\.(?:js|html)$/.test(entry.name)) files.push(filename);
        }
    };
    collect(path.join(root, 'frontend'));

    const leaks = [];
    const patterns = [
        /placeholder\s*=\s*(["'])(.*?)\1/gs,
        /placeholder\s*:\s*(["'])(.*?)\1/gs,
        /\.placeholder\s*=\s*(["'])(.*?)\1/gs,
    ];
    for (const filename of files) {
        const source = fs.readFileSync(filename, 'utf8');
        for (const pattern of patterns) {
            for (const match of source.matchAll(pattern)) {
                if (!/[\p{Script=Han}]/u.test(match[2])) continue;
                const line = source.slice(0, match.index).split('\n').length;
                leaks.push(`${path.relative(root, filename)}:${line}: ${match[2]}`);
            }
        }
    }
    assert.deepEqual(leaks, []);
});

test('runtime uses Chinese by default and persists explicit locale', () => {
    assert.equal(I18n.getLocale(), 'zh-CN');
    assert.equal(I18n.t('auth.signIn'), '登录');
    I18n.setLocale('en-US');
    assert.equal(I18n.getLocale(), 'en-US');
    assert.equal(I18n.t('auth.signIn'), 'Sign in');
    assert.equal(storage.get('dbclaw_locale'), 'en-US');
    assert.equal(document.documentElement.lang, 'en-US');
    assert.equal(I18n.t('pageCopy.hosts.loadFailed'), 'Load failed');
    assert.equal(I18n.t('pageCopy.instanceDetail.noSqlText'), 'No SQL text');
    assert.equal(I18n.t('pageCopy.users.passwordMustBeAtLeast6Characters'), 'Password must be at least 6 characters');
    assert.equal(I18n.skillCategory('通用诊断'), 'General Diagnostics');
    assert.equal(I18n.skillCategory('平台操作'), 'Platform Operations');
    assert.equal(I18n.skillCategory('OceanBase MySQL'), 'OceanBase MySQL');
    assert.equal(I18n.skillCategory('user-defined-category'), 'user-defined-category');
});

test('unsupported locales safely fall back to Chinese', () => {
    I18n.setLocale('fr-FR');
    assert.equal(I18n.getLocale(), 'zh-CN');
    assert.equal(I18n.t('common.save'), '保存');
});

test('additional locales can be registered without changing the runtime', () => {
    I18n.registerLocale('x-test', { demo: { greeting: 'Hello {name}' } }, {
        aliases: ['xt'],
        dir: 'rtl',
    });
    I18n.setLocale('xt');
    assert.equal(I18n.getLocale(), 'x-test');
    assert.equal(I18n.t('demo.greeting', { name: 'DBClaw' }), 'Hello DBClaw');
    assert.equal(document.documentElement.dir, 'rtl');
    assert.ok(I18n.supportedLocales.includes('x-test'));
    I18n.setLocale('zh-CN');
});

test('number, list and unit formatters follow the active locale', () => {
    I18n.setLocale('en-US');
    assert.equal(I18n.formatNumber(1234.5), '1,234.5');
    assert.equal(I18n.formatList(['MySQL', 'PostgreSQL']), 'MySQL and PostgreSQL');
    assert.match(I18n.formatUnit(5, 'megabyte'), /^5\s?MB$/);
    I18n.setLocale('zh-CN');
});

test('inspection system metadata follows the active locale for historical reports', () => {
    const connectionReport = {
        datasource_name: 'opengauss_5.0(58)',
        title: '连接失败巡检 - opengauss_5.0(58)',
        trigger_type: 'connection_failure',
        trigger_reason: 'Database connection failed: opengauss_5.0(58) (opengauss)',
    };
    const manualReport = {
        datasource_name: 'mysql_5.5(71:3306)',
        title: '手动巡检 - mysql_5.5(71:3306)',
        trigger_type: 'manual',
        trigger_reason: '人工触发巡检',
    };

    I18n.setLocale('en-US');
    assert.equal(inspectionPage.formatReportTitle(connectionReport), 'Connection Failure Inspection - opengauss_5.0(58)');
    assert.equal(inspectionPage.formatTriggerReason(connectionReport), 'Database connection failed: opengauss_5.0(58) (opengauss)');
    assert.equal(inspectionPage.formatReportTitle(manualReport), 'Manual Inspection - mysql_5.5(71:3306)');
    assert.equal(inspectionPage.formatTriggerReason(manualReport), 'Manual inspection');

    I18n.setLocale('zh-CN');
    assert.equal(inspectionPage.formatReportTitle(connectionReport), '连接失败巡检 - opengauss_5.0(58)');
    assert.equal(inspectionPage.formatTriggerReason(connectionReport), '数据库连接失败：opengauss_5.0(58) (opengauss)');
    assert.equal(inspectionPage.formatReportTitle(manualReport), '手动巡检 - mysql_5.5(71:3306)');
    assert.equal(inspectionPage.formatTriggerReason(manualReport), '手动触发巡检');
});

test('alert system metadata follows the active locale for historical events', () => {
    const connectionEvent = {
        alert_type: 'system_error', metric_name: 'connection_status',
        title: '数据库连接失败', trigger_reason: '数据库连接失败：authentication failed',
    };
    const thresholdEvent = {
        alert_type: 'threshold_violation', metric_name: 'disk_usage', title: 'disk_usage 阈值告警',
    };

    I18n.setLocale('en-US');
    assert.equal(alertsPage.formatAlertTitle(connectionEvent), 'Database connection failed');
    assert.equal(alertsPage.formatAlertTitle({ title: '数据库连接失败' }), 'Database connection failed');
    assert.equal(alertsPage.formatAlertTriggerReason(connectionEvent), 'Database connection failed: authentication failed');
    assert.equal(alertsPage.formatAlertTitle(thresholdEvent), 'Disk usage threshold alert');
    assert.equal(alertsPage.formatLinkedReportTitle({ trigger_type: 'anomaly', title: '异常巡检 - primary-db' }, 'primary-db'), 'Anomaly Inspection - primary-db');

    I18n.setLocale('zh-CN');
    assert.equal(alertsPage.formatAlertTitle(connectionEvent), '数据库连接失败');
    assert.equal(alertsPage.formatAlertTriggerReason(connectionEvent), '数据库连接失败：authentication failed');
    assert.equal(alertsPage.formatAlertTitle(thresholdEvent), '磁盘使用率阈值告警');
    assert.equal(alertsPage.formatLinkedReportTitle({ trigger_type: 'anomaly', title: 'Anomaly Inspection - primary-db' }, 'primary-db'), '异常巡检 - primary-db');
});

test('resource overview localizes historical alert titles and long relative times', () => {
    const createdAt = new Date(Date.now() - 20 * 24 * 60 * 60 * 1000).toISOString();

    I18n.setLocale('en-US');
    assert.equal(dashboardPage._formatAlertTitle({ title: '数据库连接失败' }), 'Database connection failed');
    assert.match(dashboardPage._relTime(createdAt), /^20 days ago$/);

    I18n.setLocale('zh-CN');
    assert.equal(dashboardPage._formatAlertTitle({ title: 'Database connection failed' }), '数据库连接失败');
    assert.match(dashboardPage._relTime(createdAt), /^20天前$/);
});
