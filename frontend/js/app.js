/* App initialization */
(function() {
    // Register routes
    Router.register('dashboard', () => { DashboardPage.render(); });
    Router.register('connections', () => { ConnectionsPage.render(); });
    Router.register('ssh-hosts', () => { SSHHostsPage.render(); });
    Router.register('monitor', () => MonitorPage.render());
    Router.register('diagnosis', () => DiagnosisPage.render());
    Router.register('query', () => QueryPage.render());
    Router.register('reports', () => ReportsPage.render());
    Router.register('ai-models', () => AIModelsPage.render());

    // Render sidebar
    Sidebar.render();

    // Load initial connections
    API.getConnections().then(connections => {
        Store.set('connections', connections);
    }).catch(() => {});

    // Initialize router (renders default page)
    Router.init();
})();
