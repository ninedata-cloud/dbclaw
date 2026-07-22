/* Lightweight i18n runtime for the Vanilla JS application. */
(function (global) {
    const STORAGE_KEY = 'dbclaw_locale';
    const DEFAULT_LOCALE = 'zh-CN';
    const catalogs = global.DBClawLocales || {};
    const localeDefinitions = {
        'zh-CN': { aliases: ['zh', 'zh-cn', 'zh-hans', 'zh-hans-cn'], labelKey: 'common.chinese', dir: 'ltr' },
        'en-US': { aliases: ['en', 'en-us'], labelKey: 'common.english', dir: 'ltr' }
    };
    let locale = DEFAULT_LOCALE;
    const metrics = { missingKey: 0, invalidLocale: 0 };

    function normalize(value) {
        if (!value) return null;
        const candidate = String(value).replace('_', '-').toLowerCase();
        for (const [code, definition] of Object.entries(localeDefinitions)) {
            if (code.toLowerCase() === candidate || definition.aliases.includes(candidate)) return code;
        }
        return null;
    }

    function registerLocale(code, catalog, definition = {}) {
        if (!code || !catalog) throw new Error('A locale code and catalog are required');
        catalogs[code] = catalog;
        localeDefinitions[code] = {
            aliases: (definition.aliases || []).map(value => String(value).toLowerCase()),
            labelKey: definition.labelKey || `languages.${code}`,
            dir: definition.dir || 'ltr'
        };
    }

    function getTimeZone() {
        const user = typeof Store !== 'undefined' ? Store.get('currentUser') : null;
        return user && user.timezone ? user.timezone : undefined;
    }

    function readStoredLocale() {
        try { return normalize(localStorage.getItem(STORAGE_KEY)); } catch (_) { return null; }
    }

    function lookup(targetLocale, key) {
        return key.split('.').reduce((value, part) => value && value[part], catalogs[targetLocale]);
    }

    function interpolate(template, params) {
        return String(template).replace(/\{([\w.]+)\}/g, (match, name) => {
            const value = params && Object.prototype.hasOwnProperty.call(params, name) ? params[name] : match;
            return value === null || value === undefined ? '' : String(value);
        });
    }

    function t(key, params = {}) {
        const value = lookup(locale, key) ?? lookup(DEFAULT_LOCALE, key);
        if (value === undefined) {
            metrics.missingKey += 1;
            console.warn(`[i18n] Missing translation key: ${key}`);
            return key;
        }
        return interpolate(value, params);
    }

    function plural(key, count, params = {}) {
        const rule = new Intl.PluralRules(locale).select(Number(count));
        const value = lookup(locale, `${key}.${rule}`) ?? lookup(locale, `${key}.other`)
            ?? lookup(DEFAULT_LOCALE, `${key}.other`);
        return value === undefined ? key : interpolate(value, { ...params, count });
    }

    const SKILL_CATEGORY_KEYS = Object.freeze({
        '通用诊断': 'generalDiagnostics',
        general: 'generalDiagnostics',
        diagnosis: 'generalDiagnostics',
        diagnostics: 'generalDiagnostics',
        '平台操作': 'platformOperations',
        system: 'platformOperations',
        '知识检索': 'knowledgeRetrieval',
        external_api: 'knowledgeRetrieval',
        '高权限操作': 'privilegedOperations',
        admin: 'privilegedOperations',
        mysql: 'mysql',
        'oceanbase mysql': 'oceanbaseMysql',
        postgresql: 'postgresql',
        sqlserver: 'sqlServer',
        'sql server': 'sqlServer',
        oracle: 'oracle',
        opengauss: 'openGauss',
        hana: 'sapHana',
        'sap hana': 'sapHana',
        monitoring: 'monitoring',
        inspection: 'inspection',
        notification: 'notification',
        query: 'query',
        custom: 'custom',
    });

    function skillCategory(value) {
        const original = String(value || '').trim();
        if (!original) return t('skills.categories.generalDiagnostics');
        const key = SKILL_CATEGORY_KEYS[original] || SKILL_CATEGORY_KEYS[original.toLowerCase()];
        return key ? t(`skills.categories.${key}`) : original;
    }

    function updateDocumentMetadata() {
        document.documentElement.lang = locale;
        document.documentElement.dir = localeDefinitions[locale]?.dir || 'ltr';
        document.title = t('app.title');
        const subtitle = document.querySelector('.sidebar-title-cn');
        if (subtitle) subtitle.textContent = t('app.subtitle');
    }

    function setLocale(value, options = {}) {
        const normalized = normalize(value);
        if (value && !normalized) {
            metrics.invalidLocale += 1;
            console.warn(`[i18n] Invalid locale: ${value}`);
        }
        const next = normalized || DEFAULT_LOCALE;
        locale = next;
        if (options.persist !== false) {
            try { localStorage.setItem(STORAGE_KEY, next); } catch (_) { /* storage is optional */ }
        }
        updateDocumentMetadata();
        document.dispatchEvent(new CustomEvent('dbclaw:localechange', { detail: { locale: next } }));
        return next;
    }

    const DirtyState = {
        _scopes: new Set(),
        mark(scope = 'page') { this._scopes.add(scope); },
        clear(scope) { scope ? this._scopes.delete(scope) : this._scopes.clear(); },
        isDirty() { return this._scopes.size > 0; }
    };

    async function switchLocale(value) {
        const next = normalize(value);
        if (!next || next === locale) return true;
        if (DirtyState.isDirty() && !global.confirm(t('language.unsavedConfirm'))) return false;
        try {
            const currentUser = typeof Store !== 'undefined' ? Store.get('currentUser') : null;
            if (currentUser && typeof API !== 'undefined') {
                const updated = await API.updateLocale(next);
                Store.set('currentUser', updated);
            }
            setLocale(next);
            DirtyState.clear();
            if (global.Modal && !DOM.$('#modal-overlay')?.classList.contains('hidden')) Modal.hide();
            if (global.Toast?.clear) Toast.clear();
            // Monaco's NLS bundle is selected by the AMD loader and cannot be
            // replaced after it has loaded. Reload only in that case; the
            // persisted session, locale, hash route and saved content survive.
            if (global.monaco) {
                global.location.reload();
                return true;
            }
            if (typeof Sidebar !== 'undefined' && currentUser) Sidebar.render();
            if (typeof Router !== 'undefined' && typeof Router.refreshCurrentRoute === 'function') await Router.refreshCurrentRoute();
            return true;
        } catch (error) {
            if (global.Toast) Toast.error(t('language.saveFailed', { message: error.message }));
            return false;
        }
    }

    function createSelector(className = '') {
        const select = document.createElement('select');
        select.className = `language-selector ${className}`.trim();
        select.setAttribute('aria-label', t('language.switch'));
        select.innerHTML = Object.entries(localeDefinitions)
            .filter(([code]) => catalogs[code])
            .map(([code, definition]) => `<option value="${code}">${t(definition.labelKey)}</option>`)
            .join('');
        select.value = locale;
        select.addEventListener('change', async () => {
            const previous = locale;
            if (!await switchLocale(select.value)) select.value = previous;
        });
        return select;
    }

    locale = readStoredLocale() || DEFAULT_LOCALE;
    global.DirtyState = DirtyState;
    global.I18n = {
        get supportedLocales() { return Object.keys(localeDefinitions).filter(code => catalogs[code]); },
        defaultLocale: DEFAULT_LOCALE,
        normalize, registerLocale, t, plural, skillCategory, getLocale: () => locale, setLocale, switchLocale,
        getMetrics: () => ({ ...metrics }),
        createSelector,
        configDescription: (key, fallback = '') => lookup(locale, `configDescriptions.${key}`) || fallback,
        formatNumber: (value, options) => new Intl.NumberFormat(locale, options).format(value),
        formatDate: (value, options = {}) => new Intl.DateTimeFormat(locale, { timeZone: getTimeZone(), ...options }).format(new Date(value)),
        formatTime: (value, options = {}) => {
            const hasFields = ['hour', 'minute', 'second'].some(key => Object.prototype.hasOwnProperty.call(options, key));
            const timeOptions = hasFields ? options : { timeStyle: 'medium', ...options };
            return new Intl.DateTimeFormat(locale, { timeZone: getTimeZone(), ...timeOptions }).format(new Date(value));
        },
        formatRelativeTime: (value, unit, options) => new Intl.RelativeTimeFormat(locale, options).format(value, unit),
        formatList: (values, options) => new Intl.ListFormat(locale, options).format(values),
        formatUnit: (value, unit, options = {}) => new Intl.NumberFormat(locale, {
            style: 'unit', unit, unitDisplay: 'short', ...options
        }).format(value)
    };

    document.addEventListener('DOMContentLoaded', () => {
        updateDocumentMetadata();
        const markDirtyFromEvent = event => {
            if (event.target.closest('#modal-container')) DirtyState.mark('modal');
            else if (event.target.closest('[data-dirty-track],.CodeMirror,.document-editor')) DirtyState.mark('page');
        };
        document.addEventListener('input', markDirtyFromEvent, true);
        document.addEventListener('change', markDirtyFromEvent, true);
    });
})(window);
