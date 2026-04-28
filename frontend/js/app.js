/* App initialization */
(async function() {
    // Register routes
    Router.register('login', () => LoginPage.render());
    Router.register('dashboard', () => { DashboardPage.render(); return () => DashboardPage._stopTimer(); });
    Router.register('datasources', () => { DatasourcesPage.render(); });
    Router.register('hosts', () => { HostsPage.render(); });
    Router.register('monitor', () => MonitorPage.render());
    Router.register('diagnosis', (routeParam) => DiagnosisPage.renderFromRoute(routeParam));
    Router.register('ai-models', () => AIModelsPage.render());
    Router.register('documents', () => DocumentsPage.render());
    Router.register('skills', () => SkillsPage.render());
    Router.register('system-configs', () => SystemConfigsPage.render());
    Router.register('scheduled-tasks', () => ScheduledTasksPage.render());
    Router.register('users', () => UsersPage.render());
    Router.register('inspection', (routeParam) => InspectionPage.renderFromRoute(routeParam));
    Router.register('alerts', (routeParam) => AlertsPage.init({ routeParam }));
    Router.register('alert-ai-policies', () => {
        Router.navigate('alerts?tab=templates');
    });
    Router.register('alert-templates', () => {
        Router.navigate('alerts?tab=templates');
    });
    Router.register('integrations', () => integrationsPage.init());
    Router.register('instance-detail', (routeParam) => InstanceDetailPage.render(routeParam));
    Router.register('host-detail', (routeParam) => HostDetailPage.render(routeParam));

    if (API.shouldRestoreSession()) {
        try {
            const currentUser = await API.getMe();
            Store.set('currentUser', currentUser);
            Sidebar.render();
            API.getDatasources().then(datasources => {
                Store.set('datasources', datasources);
            }).catch(() => {});
        } catch (e) {
            Store.set('currentUser', null);
        }
    } else {
        Store.set('currentUser', null);
    }

    // Initialize router
    Router.init();
})();
