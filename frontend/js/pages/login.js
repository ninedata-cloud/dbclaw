/* Login page */
const LoginPage = {
    render() {
        // Hide sidebar and header
        const sidebar = DOM.$('#sidebar');
        const mainContent = DOM.$('#main-content');
        const pageHeader = DOM.$('#page-header');
        if (sidebar) sidebar.style.display = 'none';
        if (pageHeader) pageHeader.style.display = 'none';
        if (mainContent) mainContent.style.marginLeft = '0';

        const content = DOM.$('#page-content');
        content.innerHTML = '';

        const page = DOM.el('div', { className: 'login-page' });
        const card = DOM.el('div', { className: 'login-card' });

        card.innerHTML = `
            <div id="login-language" class="login-language"></div>
            <div class="login-logo">
                <img src="/assets/logo-1.svg" alt="DBClaw">
                <span>DBClaw</span>
            </div>
            <div class="login-error" id="login-error"></div>
            <form class="login-form" id="login-form">
                <div class="form-group">
                    <label for="login-username">${I18n.t('auth.username')}</label>
                    <input type="text" id="login-username" placeholder="${I18n.t('auth.usernamePlaceholder')}" autocomplete="username" required>
                </div>
                <div class="form-group">
                    <label for="login-password">${I18n.t('auth.password')}</label>
                    <input type="password" id="login-password" placeholder="${I18n.t('auth.passwordPlaceholder')}" autocomplete="current-password" required>
                </div>
                <button type="submit" class="btn-login" id="login-btn">${I18n.t('auth.signIn')}</button>
            </form>
        `;

        page.appendChild(card);
        content.appendChild(page);
        DOM.$('#login-language').appendChild(I18n.createSelector('login-language-select'));

        // Wire up form
        const form = DOM.$('#login-form');
        DOM.bindAsyncSubmit(form, async () => {
            await this._handleLogin();
        }, { submitControls: [DOM.$('#login-btn')] });

        // Focus username field
        DOM.$('#login-username').focus();

        return () => {
            // Cleanup: restore sidebar and header
            if (sidebar) sidebar.style.display = '';
            if (pageHeader) pageHeader.style.display = '';
            if (mainContent) mainContent.style.marginLeft = '';
        };
    },

    async _handleLogin() {
        const username = DOM.$('#login-username').value.trim();
        const password = DOM.$('#login-password').value;
        const errorEl = DOM.$('#login-error');
        const btn = DOM.$('#login-btn');

        if (!username || !password) {
            errorEl.textContent = I18n.t('auth.required');
            errorEl.classList.add('visible');
            return;
        }

        btn.disabled = true;
        btn.textContent = I18n.t('auth.signingIn');
        errorEl.classList.remove('visible');

        try {
            const result = await API.login(username, password);
            Store.set('currentUser', result.user);
            API.markSessionAvailable();
            I18n.setLocale(result.user.locale || I18n.defaultLocale);

            // Restore sidebar and header
            const sidebar = DOM.$('#sidebar');
            const mainContent = DOM.$('#main-content');
            const pageHeader = DOM.$('#page-header');
            if (sidebar) sidebar.style.display = '';
            if (pageHeader) pageHeader.style.display = '';
            if (mainContent) mainContent.style.marginLeft = '';

            // Render sidebar and navigate
            Sidebar.render();

            // Load datasources
            API.getDatasources().then(datasources => {
                Store.set('datasources', datasources);
            }).catch(() => {});

            Router.navigate('dashboard');
        } catch (err) {
            errorEl.textContent = err.message || I18n.t('auth.failed');
            errorEl.classList.add('visible');
            btn.disabled = false;
            btn.textContent = I18n.t('auth.signIn');
        }
    }
};
