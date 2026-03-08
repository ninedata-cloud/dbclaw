/* Sidebar component */
const Sidebar = {
    navItems: [
        { section: 'Overview', items: [
            { id: 'dashboard', icon: 'layout-dashboard', label: 'Dashboard' },
            { id: 'guardian', icon: 'shield', label: 'AI Guardian' },
        ]},
        { section: 'Management', items: [
            { id: 'datasources', icon: 'database', label: 'Datasources' },
            { id: 'ssh-hosts', icon: 'terminal', label: 'SSH Hosts' },
            { id: 'monitor', icon: 'activity', label: 'Monitor' },
        ]},
        { section: 'Tools', items: [
            { id: 'diagnosis', icon: 'bot', label: 'AI Diagnosis' },
            { id: 'query', icon: 'terminal-square', label: 'Query' },
            { id: 'reports', icon: 'file-text', label: 'Reports' },
            { id: 'scheduled-reports', icon: 'calendar-clock', label: 'Scheduled Reports' },
        ]},
        { section: 'Settings', items: [
            { id: 'ai-models', icon: 'brain', label: 'AI Models' },
            { id: 'knowledge-bases', icon: 'book-open', label: 'Knowledge Bases' },
            { id: 'skills', icon: 'wrench', label: 'Skills' },
        ]},
    ],

    render() {
        const nav = DOM.$('#sidebar-nav');
        DOM.clear(nav);

        const currentUser = Store.get('currentUser');

        for (const section of this.navItems) {
            const sectionEl = DOM.el('div', { className: 'nav-section' });
            sectionEl.appendChild(DOM.el('div', { className: 'nav-section-title', textContent: section.section }));

            for (const item of section.items) {
                const navItem = DOM.el('div', {
                    className: 'nav-item',
                    dataset: { page: item.id },
                    innerHTML: `<i data-lucide="${item.icon}"></i><span>${item.label}</span>`,
                    onClick: () => Router.navigate(item.id)
                });
                sectionEl.appendChild(navItem);
            }
            nav.appendChild(sectionEl);
        }

        // Add System section for admins
        if (currentUser && currentUser.is_admin) {
            const systemSection = DOM.el('div', { className: 'nav-section' });
            systemSection.appendChild(DOM.el('div', { className: 'nav-section-title', textContent: 'System' }));
            const usersItem = DOM.el('div', {
                className: 'nav-item',
                dataset: { page: 'users' },
                innerHTML: '<i data-lucide="users"></i><span>User Management</span>',
                onClick: () => Router.navigate('users')
            });
            systemSection.appendChild(usersItem);
            nav.appendChild(systemSection);
        }

        DOM.createIcons();

        // Add user info and logout
        const footer = DOM.$('.sidebar-footer');
        if (currentUser) {
            const userInfo = DOM.el('div', { className: 'sidebar-user' });
            const avatar = DOM.el('div', { className: 'sidebar-user-avatar', textContent: currentUser.username.charAt(0).toUpperCase() });
            const info = DOM.el('div', { className: 'sidebar-user-info' });
            info.appendChild(DOM.el('div', { className: 'sidebar-user-name', textContent: currentUser.display_name || currentUser.username }));
            info.appendChild(DOM.el('div', { className: 'sidebar-user-role', textContent: currentUser.is_admin ? 'Administrator' : 'User' }));
            const logoutBtn = DOM.el('button', {
                className: 'sidebar-logout-btn',
                innerHTML: '<i data-lucide="log-out"></i>',
                title: 'Logout',
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
