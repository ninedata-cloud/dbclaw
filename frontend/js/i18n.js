/* Lightweight i18n runtime for the Vanilla JS application. */
(function (global) {
    const STORAGE_KEY = 'dbclaw_locale';
    const DEFAULT_LOCALE = 'zh-CN';
    const SUPPORTED = Object.freeze(['zh-CN', 'en-US']);
    const catalogs = global.DBClawLocales || {};
    let locale = DEFAULT_LOCALE;
    let observer = null;

    function normalize(value) {
        if (!value) return null;
        const candidate = String(value).replace('_', '-').toLowerCase();
        if (candidate === 'zh' || candidate === 'zh-cn' || candidate === 'zh-hans') return 'zh-CN';
        if (candidate === 'en' || candidate === 'en-us') return 'en-US';
        return null;
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

    function updateDocumentMetadata() {
        document.documentElement.lang = locale;
        document.title = t('app.title');
        const subtitle = document.querySelector('.sidebar-title-cn');
        if (subtitle) subtitle.textContent = t('app.subtitle');
    }

    function translateLegacyValue(value, allowPartial = false) {
        if (typeof value !== 'string' || locale === DEFAULT_LOCALE) return value;
        const direct = lookup(locale, 'legacy') || {};
        if (Object.prototype.hasOwnProperty.call(direct, value)) return direct[value];
        if (!allowPartial) return value;

        // Longest-first phrase replacement covers legacy template strings that
        // combine a UI label with dynamic values. Unknown fragments (including
        // user and database content) are deliberately preserved.
        let translatedValue = value;
        const phrases = Object.entries(direct).sort((a, b) => b[0].length - a[0].length);
        for (const [source, translated] of phrases) {
            if (source.length < 2) continue;
            if (translatedValue.includes(source)) translatedValue = translatedValue.split(source).join(translated);
        }
        // Single-character counters are safe to translate only when they are
        // used as numeric units. Replacing them globally would corrupt words
        // such as "执行" or user-provided Chinese content.
        for (const source of ['天', '分', '秒', '行', '条', '页', '项', '级']) {
            const translated = direct[source];
            if (!translated) continue;
            const unitPattern = new RegExp(`(^|\\d\\s*)${source}(?=$|[\\s\\d·|,.，。)）])`, 'g');
            translatedValue = translatedValue.replace(unitPattern, (match, prefix) => `${prefix}${translated}`);
        }
        if (translatedValue !== value && locale === 'en-US') {
            translatedValue = translatedValue
                .replace(/：\s*/g, ': ')
                .replace(/；\s*/g, '; ')
                .replace(/，\s*/g, ', ')
                .replace(/（/g, '(')
                .replace(/）/g, ')')
                .replace(/\s{2,}/g, ' ');
        }
        return translatedValue;
    }

    function looksLikeDynamicUiText(value) {
        if (!/[\u3400-\u9fff]/.test(value)) return false;
        // Interpolated UI strings usually combine translated labels with a
        // count, timestamp, status separator, or another runtime value.
        return /\d/.test(value) || /[:：·|()（）]/.test(value);
    }

    function shouldSkip(node) {
        const parent = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
        return !parent || Boolean(parent.closest(
            'script,style,code,pre,textarea,[data-i18n-ignore],.monaco-editor,.CodeMirror,.xterm'
        ));
    }

    function translateTextNode(node) {
        if (shouldSkip(node)) return;
        const raw = node.nodeValue;
        const trimmed = raw.trim();
        if (!trimmed) return;
        const parent = node.parentElement;
        const allowPartial = Boolean(parent && (
            /^(BUTTON|LABEL|TH|H1|H2|H3|H4|OPTION|SUMMARY)$/.test(parent.tagName)
            || parent.closest('[data-i18n-auto]')
            || /(?:title|label|header|hint|help|empty|loading|error|toast|modal|badge|status|toolbar|pagination|filter|action)/.test(parent.className || '')
        )) || looksLikeDynamicUiText(trimmed);
        const translated = translateLegacyValue(trimmed, allowPartial);
        if (translated !== trimmed) {
            const start = raw.slice(0, raw.indexOf(trimmed));
            const end = raw.slice(raw.indexOf(trimmed) + trimmed.length);
            node.nodeValue = start + translated + end;
        }
    }

    function translateElement(element) {
        if (shouldSkip(element)) return;
        for (const attr of ['placeholder', 'title', 'aria-label']) {
            if (!element.hasAttribute || !element.hasAttribute(attr)) continue;
            const current = element.getAttribute(attr);
            const translated = translateLegacyValue(current, true);
            if (translated !== current) element.setAttribute(attr, translated);
        }
        if (element.tagName === 'INPUT' && ['button', 'submit', 'reset'].includes(element.type)) {
            element.value = translateLegacyValue(element.value, true);
        }
    }

    function translateDom(root = document.body) {
        if (!root) return;
        if (root.nodeType === Node.TEXT_NODE) {
            translateTextNode(root);
            return;
        }
        translateElement(root);
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            if (node.nodeType === Node.TEXT_NODE) translateTextNode(node);
            else translateElement(node);
        }
    }

    function startObserver() {
        if (observer || !document.body) return;
        observer = new MutationObserver(records => {
            for (const record of records) {
                if (record.type === 'characterData') translateTextNode(record.target);
                else if (record.type === 'attributes') translateElement(record.target);
                else record.addedNodes.forEach(node => translateDom(node));
            }
        });
        observer.observe(document.body, {
            childList: true, subtree: true, characterData: true, attributes: true,
            attributeFilter: ['placeholder', 'title', 'aria-label']
        });
    }

    function setLocale(value, options = {}) {
        const next = normalize(value) || DEFAULT_LOCALE;
        locale = next;
        if (options.persist !== false) {
            try { localStorage.setItem(STORAGE_KEY, next); } catch (_) { /* storage is optional */ }
        }
        updateDocumentMetadata();
        translateDom();
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
        select.innerHTML = `
            <option value="zh-CN">${t('common.chinese')}</option>
            <option value="en-US">${t('common.english')}</option>
        `;
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
        supportedLocales: SUPPORTED,
        defaultLocale: DEFAULT_LOCALE,
        normalize, t, plural, getLocale: () => locale, setLocale, switchLocale,
        createSelector, translateDom, translateLegacyText: value => translateLegacyValue(value, true),
        configDescription: (key, fallback = '') => lookup(locale, `configDescriptions.${key}`) || fallback,
        formatNumber: (value, options) => new Intl.NumberFormat(locale, options).format(value),
        formatDate: (value, options) => new Intl.DateTimeFormat(locale, options).format(new Date(value)),
        formatTime: (value, options = {}) => {
            const hasFields = ['hour', 'minute', 'second'].some(key => Object.prototype.hasOwnProperty.call(options, key));
            return new Intl.DateTimeFormat(locale, hasFields ? options : { timeStyle: 'medium', ...options }).format(new Date(value));
        },
        formatRelativeTime: (value, unit, options) => new Intl.RelativeTimeFormat(locale, options).format(value, unit)
    };

    const nativeConfirm = global.confirm.bind(global);
    global.confirm = message => nativeConfirm(translateLegacyValue(String(message), true));

    document.addEventListener('DOMContentLoaded', () => {
        updateDocumentMetadata();
        translateDom();
        startObserver();
        const markDirtyFromEvent = event => {
            if (event.target.closest('#modal-container')) DirtyState.mark('modal');
            else if (event.target.closest('[data-dirty-track],.CodeMirror,.document-editor')) DirtyState.mark('page');
        };
        document.addEventListener('input', markDirtyFromEvent, true);
        document.addEventListener('change', markDirtyFromEvent, true);
    });
})(window);
