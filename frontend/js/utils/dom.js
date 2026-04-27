/* DOM utility helpers */
const DOM = {
    _resolveLoadingLabel(control) {
        const explicit = control?.dataset?.loadingText;
        if (explicit) return explicit;

        const baseText = String(
            control instanceof HTMLInputElement ? (control.value || '') : (control?.textContent || '')
        ).trim();
        if (!baseText) return '处理中...';
        if (/[一-龥]/.test(baseText)) {
            return `${baseText}中...`;
        }
        return `${baseText}...`;
    },

    _setControlBusy(control, busy) {
        if (!control) return;

        if (busy) {
            if (!control.dataset.domOriginalDisabled) {
                control.dataset.domOriginalDisabled = control.disabled ? '1' : '0';
            }
            if (!control.dataset.domOriginalLabel) {
                control.dataset.domOriginalLabel = control instanceof HTMLInputElement
                    ? (control.value || '')
                    : (control.innerHTML || '');
            }

            control.disabled = true;
            control.classList.add('is-loading');
            const loadingLabel = this._resolveLoadingLabel(control);

            if (control instanceof HTMLInputElement) {
                control.value = loadingLabel;
            } else {
                control.innerHTML = `<span class="spinner"></span><span>${loadingLabel}</span>`;
            }
            return;
        }

        const originalDisabled = control.dataset.domOriginalDisabled === '1';
        const originalLabel = control.dataset.domOriginalLabel;
        delete control.dataset.domOriginalDisabled;
        delete control.dataset.domOriginalLabel;

        control.disabled = originalDisabled;
        control.classList.remove('is-loading');
        if (originalLabel !== undefined) {
            if (control instanceof HTMLInputElement) {
                control.value = originalLabel;
            } else {
                control.innerHTML = originalLabel;
            }
        }
    },

    el(tag, attrs = {}, ...children) {
        const element = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs)) {
            if (key === 'className') element.className = value;
            else if (key === 'innerHTML') element.innerHTML = value;
            else if (key === 'textContent') element.textContent = value;
            else if (key.startsWith('on')) element.addEventListener(key.slice(2).toLowerCase(), value);
            else if (key === 'style' && typeof value === 'object') Object.assign(element.style, value);
            else if (key === 'dataset') Object.assign(element.dataset, value);
            else element.setAttribute(key, value);
        }
        for (const child of children) {
            if (typeof child === 'string') element.appendChild(document.createTextNode(child));
            else if (child instanceof Node) element.appendChild(child);
        }
        return element;
    },

    $(selector, parent = document) {
        return parent.querySelector(selector);
    },

    $$(selector, parent = document) {
        return Array.from(parent.querySelectorAll(selector));
    },

    clear(element) {
        element.innerHTML = '';
    },

    show(element) {
        element.classList.remove('hidden');
    },

    hide(element) {
        element.classList.add('hidden');
    },

    toggle(element, show) {
        element.classList.toggle('hidden', !show);
    },

    bindAsyncSubmit(form, handler, options = {}) {
        if (!form || typeof handler !== 'function') return;

        const getSubmitControls = () => {
            const formControls = Array.from(
                form.querySelectorAll('button[type="submit"], input[type="submit"]')
            );
            const externalControls = Array.isArray(options.submitControls)
                ? options.submitControls.filter(Boolean)
                : [];
            return Array.from(new Set([...formControls, ...externalControls]));
        };

        const setBusyState = (controls, busy) => {
            controls.forEach((control) => {
                this._setControlBusy(control, busy);
            });
        };

        form.addEventListener('submit', async (event) => {
            event.preventDefault();

            if (form.dataset.submitting === '1') {
                return;
            }

            form.dataset.submitting = '1';
            const submitControls = getSubmitControls();
            setBusyState(submitControls, true);

            try {
                await handler(event);
            } finally {
                delete form.dataset.submitting;
                setBusyState(submitControls, false);
            }
        });
    },

    createIcons() {
        // Safe wrapper for lucide.createIcons()
        if (typeof lucide !== 'undefined' && lucide.createIcons) {
            lucide.createIcons();
        }
    }
};
