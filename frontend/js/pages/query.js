/* Query execution page */
const QueryPage = {
    currentAbortController: null,

    async render() {
        // Load datasources first
        let datasources = Store.get('datasources') || [];
        if (datasources.length === 0) {
            try {
                datasources = await API.getDatasources();
                Store.set('datasources', datasources);
            } catch (e) {
                console.error('[Query] Failed to load datasources:', e);
            }
        }

        // Get or auto-select current connection
        let currentConn = Store.get('currentConnection');
        if (!currentConn && datasources.length > 0) {
            currentConn = datasources[0];
            Store.set('currentConnection', currentConn);
        }

        // Header
        const headerActions = DOM.el('div', { className: 'flex gap-8' });
        const connSelect = DOM.el('select', { className: 'form-select', id: 'query-conn-select', style: { minWidth: '400px' } });
        connSelect.appendChild(DOM.el('option', { value: '', textContent: '选择数据源...' }));

        for (const c of datasources) {
            const opt = DOM.el('option', { value: c.id, textContent: `${c.name} (${c.db_type})` });
            if (currentConn && c.id === currentConn.id) opt.selected = true;
            connSelect.appendChild(opt);
        }

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
        Header.render('SQL 查询', headerActions);

        const content = DOM.$('#page-content');
        content.innerHTML = '';
        const container = DOM.el('div', { className: 'query-container' });

        // Toolbar
        const toolbar = DOM.el('div', { className: 'query-toolbar' });
        const executeBtn = DOM.el('button', {
            className: 'btn btn-primary',
            id: 'execute-btn',
            innerHTML: '<i data-lucide="play"></i> 执行 (Ctrl+Enter)',
            onClick: () => this._executeQuery()
        });
        const cancelBtn = DOM.el('button', {
            className: 'btn btn-danger',
            id: 'cancel-btn',
            innerHTML: '<i data-lucide="x-circle"></i> 取消',
            style: { display: 'none' },
            onClick: () => this._cancelQuery()
        });
        const explainBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="search"></i> 执行计划',
            onClick: () => this._explainQuery()
        });
        const historyBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="history"></i> 历史记录',
            onClick: () => this._showHistory()
        });
        const refreshSchemaBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="refresh-cw"></i> 刷新结构',
            onClick: () => this._refreshSchema()
        });
        toolbar.appendChild(executeBtn);
        toolbar.appendChild(cancelBtn);
        toolbar.appendChild(explainBtn);
        toolbar.appendChild(historyBtn);
        toolbar.appendChild(refreshSchemaBtn);

        const hint = DOM.el('span', {
            className: 'text-muted text-sm',
            style: { marginLeft: 'auto' },
            textContent: '提示: 选中SQL后执行将只执行选中部分 | 最多返回10000行'
        });
        toolbar.appendChild(hint);
        container.appendChild(toolbar);

        // Editor
        QueryEditor.create(container, 'SELECT 1;');
        QueryEditor.onExecute = () => this._executeQuery();

        // Load schema for current connection if available (wait for editor to be ready)
        setTimeout(() => {
            if (currentConn?.id) {
                this._loadSchemaForDatasource(currentConn.id);
            }
        }, 500);

        // Status bar
        const statusBar = DOM.el('div', { className: 'query-status-bar', id: 'query-status' });
        statusBar.innerHTML = '<div class="status-info"><span class="text-muted">就绪</span></div>';
        container.appendChild(statusBar);

        // Results area
        const results = DOM.el('div', { className: 'query-results', id: 'query-results' });
        results.innerHTML = `
            <div class="empty-state" style="padding:40px">
                <i data-lucide="table"></i>
                <h3>暂无结果</h3>
                <p>执行查询后结果将显示在这里</p>
            </div>
        `;
        container.appendChild(results);

        content.appendChild(container);
        DOM.createIcons();

        return () => {
            this._cancelQuery();
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
            Toast.warning('请先选择数据源');
            return;
        }

        // Invalidate cache and reload
        window.SchemaCache.invalidate(connId);
        await this._loadSchemaForDatasource(connId);
        Toast.success('结构已刷新');
    },

    _cancelQuery() {
        if (this.currentAbortController) {
            this.currentAbortController.abort();
            this.currentAbortController = null;

            const status = DOM.$('#query-status');
            const executeBtn = DOM.$('#execute-btn');
            const cancelBtn = DOM.$('#cancel-btn');

            if (status) {
                status.innerHTML = '<div class="status-info"><span style="color:var(--accent-orange)">已取消</span></div>';
            }
            if (executeBtn) {
                executeBtn.disabled = false;
            }
            if (cancelBtn) {
                cancelBtn.style.display = 'none';
            }
        }
    },

    async _executeQuery() {
        // Get selected text or full query
        const selectedSql = QueryEditor.getSelectedText();
        const sql = (selectedSql || QueryEditor.getValue()).trim();

        if (!sql) {
            Toast.warning('请输入 SQL 查询');
            return;
        }

        const conn = Store.get('currentConnection');
        const connSelect = DOM.$('#query-conn-select');
        const connId = conn?.id || parseInt(connSelect?.value);
        if (!connId) {
            Toast.warning('请先选择数据源');
            return;
        }

        const status = DOM.$('#query-status');
        const results = DOM.$('#query-results');
        const executeBtn = DOM.$('#execute-btn');
        const cancelBtn = DOM.$('#cancel-btn');

        // Show executing state
        status.innerHTML = '<div class="status-info"><span><div class="spinner" style="display:inline-block;width:14px;height:14px;margin-right:8px"></div>执行中...</span></div>';
        results.innerHTML = '';
        executeBtn.disabled = true;
        cancelBtn.style.display = 'inline-flex';

        // Create abort controller for cancellation
        this.currentAbortController = new AbortController();

        try {
            const result = await API.executeQuery(
                { datasource_id: connId, sql, max_rows: 10000 },
                { signal: this.currentAbortController.signal }
            );

            if (result.columns && result.columns.length > 0) {
                results.innerHTML = '';
                results.appendChild(DataTable.create(result.columns, result.rows));
            } else if (result.message) {
                results.innerHTML = `<div class="empty-state" style="padding:20px"><p>${result.message}</p></div>`;
            }

            const statusText = `${result.row_count} 行 | ${result.execution_time_ms}ms${result.truncated ? ' | 已截断至10000行' : ''}`;
            status.innerHTML = `<div class="status-info"><span style="color:var(--accent-green)">${statusText}</span></div>`;
        } catch (err) {
            if (err.name === 'AbortError') {
                // Query was cancelled, status already updated in _cancelQuery
                return;
            }
            results.innerHTML = `<div style="padding:20px;color:var(--accent-red);font-family:var(--font-mono);font-size:13px;white-space:pre-wrap">${err.message}</div>`;
            status.innerHTML = '<div class="status-info"><span style="color:var(--accent-red)">错误</span></div>';
        } finally {
            this.currentAbortController = null;
            executeBtn.disabled = false;
            cancelBtn.style.display = 'none';
        }
    },

    async _explainQuery() {
        // Get selected text or full query
        const selectedSql = QueryEditor.getSelectedText();
        const sql = (selectedSql || QueryEditor.getValue()).trim();

        if (!sql) {
            Toast.warning('请输入 SQL 查询');
            return;
        }

        const conn = Store.get('currentConnection');
        const connSelect = DOM.$('#query-conn-select');
        const connId = conn?.id || parseInt(connSelect?.value);
        if (!connId) {
            Toast.warning('请先选择数据源');
            return;
        }

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
                container.innerHTML = '<p class="text-muted text-center">暂无查询历史</p>';
            } else {
                for (const item of history.slice(0, 20)) {
                    const row = DOM.el('div', {
                        style: { padding: '10px 0', borderBottom: '1px solid var(--border-color)', cursor: 'pointer' },
                        onClick: () => { QueryEditor.setValue(item.sql); Modal.hide(); }
                    });
                    row.innerHTML = `
                        <div class="font-mono text-sm" style="color:var(--text-primary);margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${item.sql}</div>
                        <div class="text-muted text-sm">${item.row_count} 行 | ${item.execution_time_ms}ms | ${item.executed_at || ''}</div>
                    `;
                    container.appendChild(row);
                }
            }

            Modal.show({
                title: '查询历史',
                content: container,
                footer: DOM.el('button', { className: 'btn btn-secondary', textContent: '关闭', onClick: () => Modal.hide() }),
                width: '640px'
            });
        } catch (err) {
            Toast.error('加载历史记录失败');
        }
    }
};
