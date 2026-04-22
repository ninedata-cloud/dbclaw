/* Hash-based SPA router */
const Router = {
    routes: {},
    currentCleanup: null,

    register(path, handler) {
        this.routes[path] = handler;
    },

    init() {
        window.addEventListener('hashchange', () => this._handleRoute());
        this._handleRoute();
    },

    navigate(path) {
        window.location.hash = path;
    },

    async _handleRoute() {
        const hash = window.location.hash.slice(1) || 'dashboard';
        const [pathPart, queryString = ''] = hash.split('?');
        const [page, ...params] = pathPart.split('/');
        const routeParam = queryString || params.join('/');

        const currentUser = Store.get('currentUser');
        if (page !== 'login' && !currentUser) {
            window.location.hash = 'login';
            return;
        }

        if (page === 'sqlConsole') {
            const currentDatasource =
                Store.get('currentConnection') ||
                Store.get('currentDatasource') ||
                (Store.get('datasources') || [])[0] ||
                null;

            if (currentDatasource?.id) {
                window.location.hash = `instance-detail?datasource=${currentDatasource.id}&tab=sqlConsole`;
            } else {
                window.location.hash = 'datasources';
            }
            return;
        }

        // Cleanup previous page
        if (this.currentCleanup && typeof this.currentCleanup === 'function') {
            this.currentCleanup();
            this.currentCleanup = null;
        }

        Store.set('currentPage', page);

        const handler = this.routes[page];
        if (handler) {
            const cleanup = await handler(routeParam);
            if (typeof cleanup === 'function') {
                this.currentCleanup = cleanup;
            }
        } else {
            const content = DOM.$('#page-content');
            content.innerHTML = `<div class="empty-state"><h3>Page not found</h3><p>The page "${Utils.escapeHtml(page)}" does not exist.</p></div>`;
        }

        // Update sidebar active state
        DOM.$$('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.page === page);
        });
    }
};
