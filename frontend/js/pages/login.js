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
                <img src="/assets/logo.svg" alt="DBMaster">
                <span>DBMaster</span>
            </div>
            <div class="login-error" id="login-error"></div>
            <form class="login-form" id="login-form">
                <div class="form-group">
                    <label for="login-username">Username</label>
                    <input type="text" id="login-username" placeholder="Enter username" autocomplete="username" required>
                </div>
                <div class="form-group">
                    <label for="login-password">Password</label>
                    <input type="password" id="login-password" placeholder="Enter password" autocomplete="current-password" required>
                </div>
                <button type="submit" class="btn-login" id="login-btn">Sign In</button>
            </form>
        `;

        page.appendChild(card);
        content.appendChild(page);

        // Wire up form
        const form = DOM.$('#login-form');
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            this._handleLogin();
        });

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
            errorEl.textContent = 'Please enter username and password';
            errorEl.classList.add('visible');
            return;
        }

        btn.disabled = true;
        btn.textContent = 'Signing in...';
        errorEl.classList.remove('visible');

        try {
            const result = await API.login(username, password);
            localStorage.setItem('auth_token', result.access_token);
            localStorage.setItem('auth_user', JSON.stringify(result.user));
            Store.set('currentUser', result.user);

            // Restore sidebar and header
            const sidebar = DOM.$('#sidebar');
            const mainContent = DOM.$('#main-content');
            const pageHeader = DOM.$('#page-header');
            if (sidebar) sidebar.style.display = '';
            if (pageHeader) pageHeader.style.display = '';
            if (mainContent) mainContent.style.marginLeft = '';

            // Render sidebar and navigate
            Sidebar.render();

            // Load connections
            API.getConnections().then(connections => {
                Store.set('connections', connections);
            }).catch(() => {});

            Router.navigate('dashboard');
        } catch (err) {
            errorEl.textContent = err.message || 'Login failed';
            errorEl.classList.add('visible');
            btn.disabled = false;
            btn.textContent = 'Sign In';
        }
    }
};
