/* App initialization */
(function() {
    // Register routes
    Router.register('login', () => LoginPage.render());
    Router.register('dashboard', () => { DashboardPage.render(); });
    Router.register('connections', () => { ConnectionsPage.render(); });
    Router.register('ssh-hosts', () => { SSHHostsPage.render(); });
    Router.register('monitor', () => MonitorPage.render());
    Router.register('diagnosis', () => DiagnosisPage.render());
    Router.register('query', () => QueryPage.render());
    Router.register('reports', () => ReportsPage.render());
    Router.register('ai-models', () => AIModelsPage.render());
    Router.register('knowledge-bases', () => KnowledgeBasesPage.render());
    Router.register('users', () => UsersPage.render());

    // Check auth
    const token = localStorage.getItem('auth_token');
    const userJson = localStorage.getItem('auth_user');
    if (token && userJson) {
        try {
            Store.set('currentUser', JSON.parse(userJson));
            Sidebar.render();
            API.getConnections().then(connections => {
                Store.set('connections', connections);
            }).catch(() => {});
        } catch (e) {
            localStorage.removeItem('auth_token');
            localStorage.removeItem('auth_user');
        }
    }

    // Initialize router
    Router.init();
})();
