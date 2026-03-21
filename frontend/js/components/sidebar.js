/* Sidebar component */
const Sidebar = {
    navItems: [
        { id: 'dashboard', icon: 'layout-dashboard', label: '资源大盘' },
        { id: 'inspection', icon: 'search-check', label: '智能巡检' },
        { id: 'diagnosis', icon: 'bot', label: 'AI 诊断' },
        { id: 'monitor', icon: 'activity', label: '性能监控' },
        { id: 'alerts', icon: 'bell', label: '告警管理' },
        { id: 'query', icon: 'terminal-square', label: 'SQL 查询' },
        { section: 'AI 智能体配置', items: [
            { id: 'ai-models', icon: 'brain', label: 'AI 大模型管理' },
            { id: 'skills', icon: 'wrench', label: '技能管理' },
            { id: 'knowledge-bases', icon: 'book-open', label: '知识库管理' },
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
            const info = DOM.el('div', { className: 'sidebar-user-info' });
            info.appendChild(DOM.el('div', { className: 'sidebar-user-name', textContent: currentUser.display_name || currentUser.username }));
            info.appendChild(DOM.el('div', { className: 'sidebar-user-role', textContent: currentUser.is_admin ? '管理员' : '用户管理' }));
            const logoutBtn = DOM.el('button', {
                className: 'sidebar-logout-btn',
                innerHTML: '<i data-lucide="log-out"></i>',
                title: '退出登录',
                onClick: () => this._logout()
            });
            userInfo.appendChild(avatar);
            userInfo.appendChild(info);
            userInfo.appendChild(logoutBtn);
            footer.parentNode.insertBefore(userInfo, footer);
            DOM.createIcons();
        }
    },

    _logout() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
        Store.set('currentUser', null);
        Router.navigate('login');
    }
};
