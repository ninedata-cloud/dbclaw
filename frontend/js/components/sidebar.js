/* Sidebar component */
const Sidebar = {
    navItems: [
        { section: 'Overview', items: [
            { id: 'dashboard', icon: 'layout-dashboard', label: 'Dashboard' },
        ]},
        { section: 'Management', items: [
            { id: 'connections', icon: 'database', label: 'Connections' },
            { id: 'ssh-hosts', icon: 'terminal', label: 'SSH Hosts' },
            { id: 'monitor', icon: 'activity', label: 'Monitor' },
        ]},
        { section: 'Tools', items: [
            { id: 'diagnosis', icon: 'bot', label: 'AI Diagnosis' },
            { id: 'query', icon: 'terminal-square', label: 'Query' },
            { id: 'reports', icon: 'file-text', label: 'Reports' },
        ]},
        { section: 'Settings', items: [
            { id: 'ai-models', icon: 'brain', label: 'AI Models' },
        ]},
    ],

    render() {
        const nav = DOM.$('#sidebar-nav');
        DOM.clear(nav);

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

        lucide.createIcons();
    }
};
