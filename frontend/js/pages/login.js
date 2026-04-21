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
            <div class="login-logo">
                <img src="/assets/logo-1.svg" alt="DBClaw">
                <span>DBClaw</span>
            </div>
            <div class="login-error" id="login-error"></div>
            <form class="login-form" id="login-form">
                <div class="form-group">
                    <label for="login-username">用户名</label>
                    <input type="text" id="login-username" placeholder="请输入用户名" autocomplete="username" required>
                </div>
                <div class="form-group">
                    <label for="login-password">密码</label>
                    <input type="password" id="login-password" placeholder="请输入密码" autocomplete="current-password" required>
                </div>
                <button type="submit" class="btn-login" id="login-btn">登录</button>
            </form>
        `;

        page.appendChild(card);
        content.appendChild(page);

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
            errorEl.textContent = '请输入用户名和密码';
            errorEl.classList.add('visible');
            return;
        }

        btn.disabled = true;
        btn.textContent = '登录中...';
        errorEl.classList.remove('visible');

        try {
            const result = await API.login(username, password);
            Store.set('currentUser', result.user);
            API.markSessionAvailable();

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
            errorEl.textContent = err.message || '登录失败';
            errorEl.classList.add('visible');
            btn.disabled = false;
            btn.textContent = '登录';
        }
    }
};
