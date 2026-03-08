/* Query execution page */
const QueryPage = {
    render() {
        const content = DOM.$('#page-content');

        // Header
        const headerActions = DOM.el('div', { className: 'flex gap-8' });
        const connSelect = DOM.el('select', { className: 'form-select', id: 'query-conn-select', style: { minWidth: '200px' } });
        connSelect.appendChild(DOM.el('option', { value: '', textContent: 'Select connection...' }));

        API.getDatasources().then(datasources => {
            Store.set('datasources', datasources);
            const current = Store.get('currentConnection');
            for (const c of datasources) {
                const opt = DOM.el('option', { value: c.id, textContent: `${c.name} (${c.db_type})` });
                if (current && c.id === current.id) opt.selected = true;
                connSelect.appendChild(opt);
            }
        });

        connSelect.addEventListener('change', () => {
            const id = parseInt(connSelect.value);
            if (id) {
                const conns = Store.get('datasources') || [];
                Store.set('currentConnection', conns.find(c => c.id === id));
                // Load schema for autocomplete
                this._loadSchemaForDatasource(id);
            }
        });

        headerActions.appendChild(connSelect);
        Header.render('Query', headerActions);

        content.innerHTML = '';
        const container = DOM.el('div', { className: 'query-container' });

        // Toolbar
        const toolbar = DOM.el('div', { className: 'query-toolbar' });
        const executeBtn = DOM.el('button', {
            className: 'btn btn-success',
            innerHTML: '<i data-lucide="play"></i> Execute',
            onClick: () => this._executeQuery()
        });
        const explainBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="search"></i> Explain',
            onClick: () => this._explainQuery()
        });
        const historyBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="history"></i> History',
            onClick: () => this._showHistory()
        });
        const refreshSchemaBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="refresh-cw"></i> Refresh Schema',
            onClick: () => this._refreshSchema()
        });
        toolbar.appendChild(executeBtn);
        toolbar.appendChild(explainBtn);
        toolbar.appendChild(historyBtn);
        toolbar.appendChild(refreshSchemaBtn);
        toolbar.appendChild(DOM.el('span', { className: 'text-muted text-sm', textContent: 'Ctrl+Enter to execute' }));
        container.appendChild(toolbar);

        // Editor
        QueryEditor.create(container, 'SELECT 1;');
        QueryEditor.onExecute = () => this._executeQuery();

        // Status bar
        const statusBar = DOM.el('div', { className: 'query-status-bar', id: 'query-status' });
        statusBar.innerHTML = '<div class="status-info"><span>Ready</span></div>';
        container.appendChild(statusBar);

        // Results area
        const results = DOM.el('div', { className: 'query-results', id: 'query-results' });
        results.innerHTML = `
            <div class="empty-state" style="padding:40px">
                <i data-lucide="table"></i>
                <h3>No Results</h3>
                <p>Execute a query to see results here.</p>
            </div>
        `;
        container.appendChild(results);

        content.appendChild(container);
        DOM.createIcons();

        // Load schema for current connection if available
        const currentConn = Store.get('currentConnection');
        if (currentConn?.id) {
            this._loadSchemaForDatasource(currentConn.id);
        }

        return () => {
            QueryEditor.destroy();
        };
    },

    async _loadSchemaForDatasource(datasourceId) {
        try {
            await QueryEditor.setSchema(datasourceId);
        } catch (error) {
            console.error('Error loading schema:', error);
        }
    },

    async _refreshSchema() {
        const conn = Store.get('currentConnection');
        const connSelect = DOM.$('#query-conn-select');
        const connId = conn?.id || parseInt(connSelect?.value);
        if (!connId) {
            Toast.warning('Select a connection first');
            return;
        }

        // Invalidate cache and reload
        window.SchemaCache.invalidate(connId);
        await this._loadSchemaForDatasource(connId);
        Toast.success('Schema refreshed');
    },

    async _executeQuery() {
        const sql = QueryEditor.getValue().trim();
        if (!sql) { Toast.warning('Enter a SQL query'); return; }

        const conn = Store.get('currentConnection');
        const connSelect = DOM.$('#query-conn-select');
        const connId = conn?.id || parseInt(connSelect?.value);
        if (!connId) { Toast.warning('Select a connection first'); return; }

        const status = DOM.$('#query-status');
        const results = DOM.$('#query-results');
        status.innerHTML = '<div class="status-info"><span><div class="spinner" style="display:inline-block;width:14px;height:14px"></div> Executing...</span></div>';
        results.innerHTML = '';

        try {
            const result = await API.executeQuery({ datasource_id: connId, sql, max_rows: 1000 });

            if (result.columns && result.columns.length > 0) {
                results.innerHTML = '';
                results.appendChild(DataTable.create(result.columns, result.rows));
            } else if (result.message) {
                results.innerHTML = `<div class="empty-state" style="padding:20px"><p>${result.message}</p></div>`;
            }

            const statusText = `${result.row_count} row(s) | ${result.execution_time_ms}ms${result.truncated ? ' | Truncated' : ''}`;
            status.innerHTML = `<div class="status-info"><span style="color:var(--accent-green)">${statusText}</span></div>`;
        } catch (err) {
            results.innerHTML = `<div style="padding:20px;color:var(--accent-red);font-family:var(--font-mono);font-size:13px">${err.message}</div>`;
            status.innerHTML = '<div class="status-info"><span style="color:var(--accent-red)">Error</span></div>';
        }
    },

    async _explainQuery() {
        const sql = QueryEditor.getValue().trim();
        if (!sql) { Toast.warning('Enter a SQL query'); return; }

        const conn = Store.get('currentConnection');
        const connSelect = DOM.$('#query-conn-select');
        const connId = conn?.id || parseInt(connSelect?.value);
        if (!connId) { Toast.warning('Select a connection first'); return; }

        const results = DOM.$('#query-results');
        results.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const result = await API.explainQuery({ datasource_id: connId, sql });
            results.innerHTML = '';

            if (result.columns && result.rows) {
                results.appendChild(DataTable.create(result.columns, result.rows));
            } else if (result.plan) {
                const pre = DOM.el('div', { className: 'explain-panel', textContent: JSON.stringify(result.plan, null, 2) });
                results.appendChild(pre);
            } else {
                const pre = DOM.el('div', { className: 'explain-panel', textContent: JSON.stringify(result, null, 2) });
                results.appendChild(pre);
            }
        } catch (err) {
            results.innerHTML = `<div style="padding:20px;color:var(--accent-red)">${err.message}</div>`;
        }
    },

    async _showHistory() {
        try {
            const history = await API.getQueryHistory();
            const container = DOM.el('div');

            if (history.length === 0) {
                container.innerHTML = '<p class="text-muted text-center">No query history</p>';
            } else {
                for (const item of history.slice(0, 20)) {
                    const row = DOM.el('div', {
                        style: { padding: '10px 0', borderBottom: '1px solid var(--border-color)', cursor: 'pointer' },
                        onClick: () => { QueryEditor.setValue(item.sql); Modal.hide(); }
                    });
                    row.innerHTML = `
                        <div class="font-mono text-sm" style="color:var(--text-primary);margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${item.sql}</div>
                        <div class="text-muted text-sm">${item.row_count} rows | ${item.execution_time_ms}ms | ${item.executed_at || ''}</div>
                    `;
                    container.appendChild(row);
                }
            }

            Modal.show({
                title: 'Query History',
                content: container,
                footer: DOM.el('button', { className: 'btn btn-secondary', textContent: 'Close', onClick: () => Modal.hide() }),
                width: '640px'
            });
        } catch (err) {
            Toast.error('Failed to load history');
        }
    }
};
