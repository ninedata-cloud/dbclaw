/* App initialization */
(function() {
    // Register routes
    Router.register('login', () => LoginPage.render());
    Router.register('dashboard', () => { DashboardPage.render(); return () => DashboardPage._stopTimer(); });
    Router.register('datasources', () => { DatasourcesPage.render(); });
    Router.register('hosts', () => { HostsPage.render(); });
    Router.register('monitor', () => MonitorPage.render());
    Router.register('diagnosis', () => DiagnosisPage.render());
    Router.register('query', () => QueryPage.render());
    Router.register('ai-models', () => AIModelsPage.render());
    Router.register('documents', () => DocumentsPage.render());
    Router.register('skills', () => SkillsPage.render());
    Router.register('system-configs', () => SystemConfigsPage.render());
    Router.register('users', () => UsersPage.render());
    Router.register('inspection', () => InspectionPage.render());
    Router.register('alerts', () => AlertsPage.init());
    Router.register('integrations', () => integrationsPage.init());

    // Check auth
    const token = localStorage.getItem('auth_token');
    const userJson = localStorage.getItem('auth_user');
    if (token && userJson) {
        try {
            Store.set('currentUser', JSON.parse(userJson));
            Sidebar.render();
            API.getDatasources().then(datasources => {
                Store.set('datasources', datasources);
            }).catch(() => {});
        } catch (e) {
            localStorage.removeItem('auth_token');
            localStorage.removeItem('auth_user');
        }
    }

    // Initialize router
    Router.init();
})();
