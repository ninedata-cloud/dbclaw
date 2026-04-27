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
        { id: 'dashboard', icon: 'layout-dashboard', label: '资源大盘' },
        { id: 'instance-detail', icon: 'panel-left', label: '实例详情' },
        { id: 'host-detail', icon: 'server', label: '主机详情' },
        { id: 'inspection', icon: 'search-check', label: '智能巡检' },
        { id: 'alerts', icon: 'bell', label: '告警管理' },
        { section: 'AI 智能体配置', items: [
            { id: 'ai-models', icon: 'brain', label: 'AI 大模型管理' },
            { id: 'skills', icon: 'wrench', label: '技能管理' },
            { id: 'documents', icon: 'book-open', label: '知识库' },
        ]},
        { section: '系统配置', items: [
            { id: 'datasources', icon: 'database', label: '数据源管理' },
            { id: 'hosts', icon: 'terminal', label: '主机管理' },
            { id: 'integrations', icon: 'package', label: '外部集成管理' },
            { id: 'system-configs', icon: 'settings', label: '系统参数配置' },
        ]},
    ],

    render() {
        const nav = DOM.$('#sidebar-nav');
        DOM.clear(nav);
        this._loadAppVersion();

        const currentUser = Store.get('currentUser');

        for (const item of this.navItems) {
            // Check if this is a section with items or a flat item
            if (item.section && item.items) {
                // Render section with items
                const sectionEl = DOM.el('div', { className: 'nav-section' });
                sectionEl.appendChild(DOM.el('div', { className: 'nav-section-title', textContent: item.section }));

                for (const subItem of item.items) {
                    const navItem = DOM.el('div', {
                        className: 'nav-item',
                        dataset: { page: subItem.id },
                        innerHTML: `<i data-lucide="${subItem.icon}"></i><span>${subItem.label}</span>`,
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
                    innerHTML: `<i data-lucide="${item.icon}"></i><span>${item.label}</span>`,
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
                    innerHTML: '<i data-lucide="users"></i><span>用户管理</span>',
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
            info.appendChild(DOM.el('div', { className: 'sidebar-user-role', textContent: currentUser.is_admin ? '管理员' : '普通用户' }));
            const menu = DOM.el('div', {
                className: 'sidebar-user-menu ds-more-menu',
                id: 'sidebar-user-menu',
                style: { display: 'none' }
            });
            menu.innerHTML = `
                <div class="ds-more-menu-item" data-action="profile" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:var(--text-primary);white-space:nowrap;">
                    <i data-lucide="user" style="width:14px;height:14px;"></i> 修改个人资料
                </div>
                <div class="ds-more-menu-item" data-action="password" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:var(--text-primary);white-space:nowrap;">
                    <i data-lucide="key-round" style="width:14px;height:14px;"></i> 修改密码
                </div>
                <div style="border-top:1px solid var(--border-color);margin:4px 0;"></div>
                <div class="ds-more-menu-item" data-action="logout" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:#ef4444;white-space:nowrap;">
                    <i data-lucide="log-out" style="width:14px;height:14px;"></i> 退出登录
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
            versionNode.title = commit ? `版本 ${version} (${commit})` : `版本 ${version}`;
        };

        try {
            const appInfo = await API.getAppInfo();
            renderVersion(appInfo);
            this._appInfoLoaded = true;
        } catch (error) {
            console.error('Failed to load app version:', error);
            renderVersion(window.DBCLAW_APP_INFO || {});
            versionNode.title = `${versionNode.title}（接口加载失败，使用页面内置版本）`;
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
            title: this._collapsed ? '展开侧边栏' : '收起侧边栏',
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
            toggleBtn.title = this._collapsed ? '展开侧边栏' : '收起侧边栏';
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
        menu.style.top = `${rect.top - 4 - 132}px`;
        menu.style.left = `${Math.max(8, rect.left)}px`;
        menu.style.display = 'block';
        DOM.createIcons();

        const handler = () => {
            this._closeUserMenu();
            document.removeEventListener('click', handler, true);
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
                <label>用户名</label>
                <input type="text" class="form-input" value="${Utils.escapeHtml(currentUser.username)}" disabled>
            </div>
            <div class="form-group">
                <label>显示名称</label>
                <input type="text" id="profile-display-name" class="form-input" placeholder="显示名称（可选）" value="${Utils.escapeHtml(currentUser.display_name || '')}">
            </div>
            <div class="form-group">
                <label>邮箱</label>
                <input type="email" id="profile-email" class="form-input" placeholder="邮箱（可选）" value="${Utils.escapeHtml(currentUser.email || '')}">
            </div>
            <div class="form-group">
                <label>电话</label>
                <input type="text" id="profile-phone" class="form-input" placeholder="电话（可选）" value="${Utils.escapeHtml(currentUser.phone || '')}">
                <div class="sidebar-profile-hint">列表默认脱敏展示：${Utils.escapeHtml(this._maskPhone(currentUser.phone))}</div>
            </div>
        `;

        Modal.show({
            title: '修改个人资料',
            content: form,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '保存', variant: 'primary', onClick: () => this._saveProfile() },
            ]
        });
    },

    _showChangePasswordModal() {
        const form = DOM.el('div');
        form.innerHTML = `
            <div class="form-group">
                <label>当前密码</label>
                <input type="password" id="profile-old-password" class="form-input" placeholder="当前密码">
            </div>
            <div class="form-group">
                <label>新密码</label>
                <input type="password" id="profile-new-password" class="form-input" placeholder="新密码（至少 6 位）">
            </div>
            <div class="form-group">
                <label>确认新密码</label>
                <input type="password" id="profile-confirm-password" class="form-input" placeholder="再次输入新密码">
            </div>
        `;

        Modal.show({
            title: '修改密码',
            content: form,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '确认修改', variant: 'primary', onClick: () => this._changeOwnPassword() },
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
            Toast.success('个人信息已更新');
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async _changeOwnPassword() {
        const oldPassword = DOM.$('#profile-old-password').value;
        const newPassword = DOM.$('#profile-new-password').value;
        const confirmPassword = DOM.$('#profile-confirm-password').value;

        if (!oldPassword || !newPassword || !confirmPassword) {
            Toast.error('请完整填写密码信息');
            return;
        }
        if (newPassword.length < 6) {
            Toast.error('新密码不能少于 6 位');
            return;
        }
        if (newPassword !== confirmPassword) {
            Toast.error('两次输入的新密码不一致');
            return;
        }

        try {
            await API.changePassword(oldPassword, newPassword);
            Modal.hide();
            Toast.success('密码已修改，请重新登录');
            Store.set('currentUser', null);
            API.clearSessionMark();
            Router.navigate('login');
        } catch (err) {
            Toast.error(err.message);
        }
    },

    _logout() {
        Modal.show({
            title: '确认退出',
            content: '<p>确定退出当前登录会话吗？</p>',
            size: 'small',
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '退出', variant: 'danger', onClick: () => this._confirmLogout() },
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
