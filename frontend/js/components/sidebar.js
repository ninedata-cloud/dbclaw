/* Sidebar component */
const Sidebar = {
    _collapsed: false,
    _appInfoLoaded: false,

    _maskPhone(phone) {
        if (!phone) return '-';
        const trimmed = String(phone).trim();
        if (trimmed.length < 7) return trimmed;
        return `${trimmed.slice(0, 3)}****${trimmed.slice(-4)}`;
    },

    navItems: [
        { id: 'dashboard', icon: 'layout-dashboard', labelKey: 'navigation.dashboard' },
        { id: 'instance-detail', icon: 'panel-left', labelKey: 'navigation.instanceDetail' },
        { id: 'host-detail', icon: 'server', labelKey: 'navigation.hostDetail' },
        { id: 'inspection', icon: 'search-check', labelKey: 'navigation.inspection' },
        { id: 'alerts', icon: 'bell', labelKey: 'navigation.alerts' },
        { sectionKey: 'navigation.aiSection', items: [
            { id: 'ai-models', icon: 'brain', labelKey: 'navigation.aiModels' },
            { id: 'skills', icon: 'wrench', labelKey: 'navigation.skills' },
            { id: 'documents', icon: 'book-open', labelKey: 'navigation.documents' },
            { id: 'evaluation', icon: 'gauge', labelKey: 'navigation.evaluation' },
        ]},
        { sectionKey: 'navigation.systemSection', items: [
            { id: 'datasources', icon: 'database', labelKey: 'navigation.datasources' },
            { id: 'hosts', icon: 'terminal', labelKey: 'navigation.hosts' },
            { id: 'integrations', icon: 'package', labelKey: 'navigation.integrations' },
            { id: 'scheduled-tasks', icon: 'calendar-clock', labelKey: 'navigation.scheduledTasks' },
            { id: 'system-configs', icon: 'settings', labelKey: 'navigation.systemConfigs' },
        ]},
    ],

    render() {
        const nav = DOM.$('#sidebar-nav');
        DOM.clear(nav);
        this._loadAppVersion();

        const currentUser = Store.get('currentUser');

        for (const item of this.navItems) {
            // Check if this is a section with items or a flat item
            if (item.sectionKey && item.items) {
                // Render section with items
                const sectionEl = DOM.el('div', { className: 'nav-section' });
                sectionEl.appendChild(DOM.el('div', { className: 'nav-section-title', textContent: I18n.t(item.sectionKey) }));

                for (const subItem of item.items) {
                    const navItem = DOM.el('div', {
                        className: 'nav-item',
                        dataset: { page: subItem.id },
                        innerHTML: `<i data-lucide="${subItem.icon}"></i><span>${I18n.t(subItem.labelKey)}</span>`,
                        onClick: () => Router.navigate(subItem.id)
                    });
                    sectionEl.appendChild(navItem);
                }
                nav.appendChild(sectionEl);
            } else {
                // Render flat item
                const navItem = DOM.el('div', {
                    className: 'nav-item',
                    dataset: { page: item.id },
                    innerHTML: `<i data-lucide="${item.icon}"></i><span>${I18n.t(item.labelKey)}</span>`,
                    onClick: () => Router.navigate(item.id)
                });
                nav.appendChild(navItem);
            }
        }

        // Add User Management to Configuration section for admins
        if (currentUser && currentUser.is_admin) {
            // Find the Configuration section
            const configSection = nav.querySelector('.nav-section:last-child');
            if (configSection) {
                const usersItem = DOM.el('div', {
                    className: 'nav-item',
                    dataset: { page: 'users' },
                    innerHTML: `<i data-lucide="users"></i><span>${I18n.t('navigation.users')}</span>`,
                    onClick: () => Router.navigate('users')
                });
                configSection.appendChild(usersItem);
            }
        }

        DOM.createIcons();

        // Add user info and logout
        const footer = DOM.$('.sidebar-footer');
        if (currentUser) {
            // Remove existing user info if present
            const existingUserInfo = DOM.$('.sidebar-user');
            if (existingUserInfo) {
                existingUserInfo.remove();
            }

            const userInfo = DOM.el('div', { className: 'sidebar-user' });
            const avatar = DOM.el('div', { className: 'sidebar-user-avatar', textContent: currentUser.username.charAt(0).toUpperCase() });
            const info = DOM.el('button', {
                className: 'sidebar-user-info',
                type: 'button',
                onClick: (event) => this._toggleUserMenu(event)
            });
            info.appendChild(DOM.el('div', { className: 'sidebar-user-name', textContent: currentUser.display_name || currentUser.username }));
            info.appendChild(DOM.el('div', { className: 'sidebar-user-role', textContent: currentUser.is_admin ? I18n.t('profile.administrator') : I18n.t('profile.user') }));
            const menu = DOM.el('div', {
                className: 'sidebar-user-menu ds-more-menu',
                id: 'sidebar-user-menu',
                style: { display: 'none' }
            });
            menu.innerHTML = `
                <div class="ds-more-menu-item" data-action="profile" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:var(--text-primary);white-space:nowrap;">
                    <i data-lucide="user" style="width:14px;height:14px;"></i> ${I18n.t('profile.editProfile')}
                </div>
                <div class="ds-more-menu-item" data-action="password" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:var(--text-primary);white-space:nowrap;">
                    <i data-lucide="key-round" style="width:14px;height:14px;"></i> ${I18n.t('profile.changePassword')}
                </div>
                <div class="ds-more-menu-item sidebar-language-item" data-action="language" style="display:flex;align-items:center;gap:8px;padding:8px 14px;font-size:13px;color:var(--text-primary);white-space:nowrap;">
                    <i data-lucide="languages" style="width:14px;height:14px;"></i>
                    <span>${I18n.t('common.language')}</span>
                </div>
                <div style="border-top:1px solid var(--border-color);margin:4px 0;"></div>
                <div class="ds-more-menu-item" data-action="logout" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:#ef4444;white-space:nowrap;">
                    <i data-lucide="log-out" style="width:14px;height:14px;"></i> ${I18n.t('profile.logout')}
                </div>
            `;
            menu.querySelector('[data-action="profile"]').onclick = () => {
                this._closeUserMenu();
                this._showProfileModal();
            };
            menu.querySelector('[data-action="password"]').onclick = () => {
                this._closeUserMenu();
                this._showChangePasswordModal();
            };
            menu.querySelector('[data-action="language"]').appendChild(I18n.createSelector('sidebar-language-select'));
            menu.querySelector('[data-action="logout"]').onclick = () => {
                this._closeUserMenu();
                this._logout();
            };
            userInfo.appendChild(avatar);
            userInfo.appendChild(info);
            userInfo.appendChild(menu);
            footer.parentNode.insertBefore(userInfo, footer);
            DOM.createIcons();
        }

        // Add toggle button
        this._renderToggleButton();
    },

    async _loadAppVersion() {
        const versionNode = DOM.$('#sidebar-version');
        if (!versionNode) return;

        if (this._appInfoLoaded) return;

        const renderVersion = (appInfo = {}) => {
            const version = (appInfo?.app_version || 'dev').trim();
            const commit = (appInfo?.build_commit || '').trim();
            const displayVersion = version.startsWith('v') ? version : `v${version}`;
            versionNode.textContent = displayVersion;
            const versionText = I18n.t('profile.version', { version });
            versionNode.title = commit ? `${versionText} (${commit})` : versionText;
        };

        try {
            const appInfo = await API.getAppInfo();
            renderVersion(appInfo);
            this._appInfoLoaded = true;
        } catch (error) {
            console.error('Failed to load app version:', error);
            renderVersion(window.DBCLAW_APP_INFO || {});
            versionNode.title = I18n.t('profile.versionFallback', { version: versionNode.title });
        }
    },

    _renderToggleButton() {
        const footer = DOM.$('.sidebar-footer');
        if (!footer) return;

        // Remove existing toggle button
        const existingBtn = DOM.$('.sidebar-toggle');
        if (existingBtn) existingBtn.remove();

        const toggleBtn = DOM.el('button', {
            className: 'sidebar-toggle',
            title: this._collapsed ? I18n.t('profile.expand') : I18n.t('profile.collapse'),
            innerHTML: `<i data-lucide="chevrons-left"></i>`,
            onClick: () => this.toggle()
        });
        footer.appendChild(toggleBtn);
        DOM.createIcons();
    },

    toggle() {
        this._collapsed = !this._collapsed;
        const sidebar = DOM.$('#sidebar');
        const mainContent = DOM.$('#main-content');

        if (this._collapsed) {
            sidebar.classList.add('collapsed');
            mainContent.style.marginLeft = 'var(--sidebar-collapsed-width)';
        } else {
            sidebar.classList.remove('collapsed');
            mainContent.style.marginLeft = 'var(--sidebar-width)';
        }

        // Update toggle button title
        const toggleBtn = DOM.$('.sidebar-toggle');
        if (toggleBtn) {
            toggleBtn.title = this._collapsed ? I18n.t('profile.expand') : I18n.t('profile.collapse');
        }

        // Re-render icons after toggle
        DOM.createIcons();
    },

    _toggleUserMenu(event) {
        event.stopPropagation();
        const menu = document.getElementById('sidebar-user-menu');
        if (!menu) return;

        const isOpen = menu.style.display !== 'none';
        this._closeUserMenu();
        if (isOpen) return;

        const btn = event.currentTarget;
        const rect = btn.getBoundingClientRect();
        menu.style.position = 'fixed';
        const menuHeight = menu.scrollHeight || 188;
        menu.style.top = `${Math.max(8, rect.top - 4 - menuHeight)}px`;
        menu.style.left = `${Math.max(8, rect.left)}px`;
        menu.style.display = 'block';
        DOM.createIcons();

        const handler = (outsideEvent) => {
            // This listener runs during capture. Keep the menu open for clicks
            // inside it so native controls (notably the language <select>) can
            // finish their default interaction before anything is hidden.
            if (menu.contains(outsideEvent.target) || btn.contains(outsideEvent.target)) return;
            this._closeUserMenu();
        };
        this._userMenuOutsideHandler = handler;
        document.addEventListener('click', handler, true);
    },

    _closeUserMenu() {
        const menu = document.getElementById('sidebar-user-menu');
        if (menu) {
            menu.style.display = 'none';
        }
        if (this._userMenuOutsideHandler) {
            document.removeEventListener('click', this._userMenuOutsideHandler, true);
            this._userMenuOutsideHandler = null;
        }
    },

    _showProfileModal() {
        const currentUser = Store.get('currentUser');
        if (!currentUser) return;

        const form = DOM.el('div');
        form.innerHTML = `
            <div class="form-group">
                <label>${I18n.t('profile.username')}</label>
                <input type="text" class="form-input" value="${Utils.escapeHtml(currentUser.username)}" disabled>
            </div>
            <div class="form-group">
                <label>${I18n.t('profile.displayName')}</label>
                <input type="text" id="profile-display-name" class="form-input" placeholder="${I18n.t('profile.displayNamePlaceholder')}" value="${Utils.escapeHtml(currentUser.display_name || '')}">
            </div>
            <div class="form-group">
                <label>${I18n.t('profile.email')}</label>
                <input type="email" id="profile-email" class="form-input" placeholder="${I18n.t('profile.emailPlaceholder')}" value="${Utils.escapeHtml(currentUser.email || '')}">
            </div>
            <div class="form-group">
                <label>${I18n.t('profile.phone')}</label>
                <input type="text" id="profile-phone" class="form-input" placeholder="${I18n.t('profile.phonePlaceholder')}" value="${Utils.escapeHtml(currentUser.phone || '')}">
                <div class="sidebar-profile-hint">${I18n.t('profile.maskedPhoneHint', { phone: Utils.escapeHtml(this._maskPhone(currentUser.phone)) })}</div>
            </div>
        `;

        Modal.show({
            title: I18n.t('profile.editProfile'),
            content: form,
            buttons: [
                { text: I18n.t('common.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('common.save'), variant: 'primary', onClick: () => this._saveProfile() },
            ]
        });
    },

    _showChangePasswordModal() {
        const form = DOM.el('div');
        form.innerHTML = `
            <div class="form-group">
                <label>${I18n.t('profile.currentPassword')}</label>
                <input type="password" id="profile-old-password" class="form-input" placeholder="${I18n.t('profile.currentPassword')}">
            </div>
            <div class="form-group">
                <label>${I18n.t('profile.newPassword')}</label>
                <input type="password" id="profile-new-password" class="form-input" placeholder="${I18n.t('profile.newPasswordPlaceholder')}">
            </div>
            <div class="form-group">
                <label>${I18n.t('profile.confirmPassword')}</label>
                <input type="password" id="profile-confirm-password" class="form-input" placeholder="${I18n.t('profile.confirmPasswordPlaceholder')}">
            </div>
        `;

        Modal.show({
            title: I18n.t('profile.changePassword'),
            content: form,
            buttons: [
                { text: I18n.t('common.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('profile.confirmChange'), variant: 'primary', onClick: () => this._changeOwnPassword() },
            ]
        });
    },

    async _saveProfile() {
        const display_name = DOM.$('#profile-display-name').value.trim();
        const email = DOM.$('#profile-email').value.trim();
        const phone = DOM.$('#profile-phone').value.trim();

        try {
            const currentUser = await API.updateMe({
                display_name: display_name || null,
                email: email || null,
                phone: phone || null,
            });
            Store.set('currentUser', currentUser);
            Modal.hide();
            Sidebar.render();
            Toast.success(I18n.t('profile.profileUpdated'));
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async _changeOwnPassword() {
        const oldPassword = DOM.$('#profile-old-password').value;
        const newPassword = DOM.$('#profile-new-password').value;
        const confirmPassword = DOM.$('#profile-confirm-password').value;

        if (!oldPassword || !newPassword || !confirmPassword) {
            Toast.error(I18n.t('profile.passwordRequired'));
            return;
        }
        if (newPassword.length < 6) {
            Toast.error(I18n.t('profile.passwordTooShort'));
            return;
        }
        if (newPassword !== confirmPassword) {
            Toast.error(I18n.t('profile.passwordsMismatch'));
            return;
        }

        try {
            await API.changePassword(oldPassword, newPassword);
            Modal.hide();
            Toast.success(I18n.t('profile.passwordChanged'));
            Store.set('currentUser', null);
            API.clearSessionMark();
            Router.navigate('login');
        } catch (err) {
            Toast.error(err.message);
        }
    },

    _logout() {
        Modal.show({
            title: I18n.t('profile.logoutTitle'),
            content: `<p>${I18n.t('profile.logoutConfirm')}</p>`,
            size: 'small',
            buttons: [
                { text: I18n.t('common.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('profile.logoutAction'), variant: 'danger', onClick: () => this._confirmLogout() },
            ]
        });
    },

    async _confirmLogout() {
        try {
            await API.logout();
        } catch (e) {
            // ignore logout errors and clear local state anyway
        }
        Modal.hide();
        Store.set('currentUser', null);
        API.clearSessionMark();
        Router.navigate('login');
    }
};
