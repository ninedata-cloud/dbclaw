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
global.MutationObserver = class MutationObserver {};
global.Node = { ELEMENT_NODE: 1, TEXT_NODE: 3 };
global.NodeFilter = { SHOW_ELEMENT: 1, SHOW_TEXT: 4 };
global.confirm = () => true;

for (const file of [
    'frontend/js/locales/zh-CN.js',
    'frontend/js/locales/en-US.js',
    'frontend/js/locales/generated-ui.js',
    'frontend/js/i18n.js'
]) {
    vm.runInThisContext(fs.readFileSync(path.join(root, file), 'utf8'), { filename: file });
}

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

test('English catalog values do not contain Han characters except the Chinese language label', () => {
    function visit(value, key = '') {
        if (value && typeof value === 'object') {
            for (const [childKey, child] of Object.entries(value)) visit(child, `${key}.${childKey}`);
            return;
        }
        if (key === '.common.chinese') return;
        assert.equal(/[\p{Script=Han}]/u.test(String(value)), false, `${key}: ${value}`);
    }
    // Legacy catalog keys are Chinese source strings; only values are visited.
    visit(DBClawLocales['en-US']);
});

test('all first-party JavaScript UI fragments are registered in the locale catalogs', () => {
    const output = execFileSync(process.execPath, [path.join(root, 'scripts/i18n-ui-audit.js'), 'frontend/js'], {
        cwd: root,
        encoding: 'utf8',
    });
    assert.deepEqual(JSON.parse(output), []);
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
    assert.equal(I18n.translateLegacyText('加载配置失败'), 'Could not load configurations');
    assert.equal(I18n.translateLegacyText('3 天 4 小时'), '3 day 4 hours');
    assert.equal(I18n.translateLegacyText('已选择 3 项'), 'Selected 3 item');
    assert.equal(I18n.translateLegacyText('例如：https://api.example.com'), 'For example: https://api.example.com');
});

test('unsupported locales safely fall back to Chinese', () => {
    I18n.setLocale('fr-FR');
    assert.equal(I18n.getLocale(), 'zh-CN');
    assert.equal(I18n.t('common.save'), '保存');
});
