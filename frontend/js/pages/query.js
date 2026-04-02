/* Query execution page */
const QueryPage = {
    currentAbortController: null,
    datasourceSelector: null,
    editorHeight: 400,
    isResizing: false,
    startY: 0,
    startHeight: 0,

    _getSelectedDatasource() {
        return this.datasourceSelector?.getValue() || Store.get('currentConnection') || null;
    },

    _getSelectedDatasourceId() {
        return this._getSelectedDatasource()?.id || null;
    },

    async render() {
        let datasources = Store.get('datasources') || [];
        if (datasources.length === 0) {
            try {
                datasources = await API.getDatasources();
                Store.set('datasources', datasources);
            } catch (e) {
                console.error('[Query] Failed to load datasources:', e);
            }
        }

        let currentConn = Store.get('currentConnection');
        if (!currentConn && datasources.length > 0) {
            currentConn = datasources[0];
            Store.set('currentConnection', currentConn);
        }

        const headerActions = DOM.el('div', { className: 'flex gap-8', style: { flex: '1', minWidth: '0' } });
        const datasourceContainer = DOM.el('div', {
            id: 'query-datasource-selector',
            style: { minWidth: '280px', maxWidth: '380px', flex: '1' }
        });
        headerActions.appendChild(datasourceContainer);
        Header.render('SQL 查询', headerActions);

        this.datasourceSelector?.destroy();
        this.datasourceSelector = new DatasourceSelector({
            container: datasourceContainer,
            allowEmpty: false,
            placeholder: '选择数据源',
            showStatus: true,
            showDetails: true,
            onLoad: (loadedDatasources) => {
                if ((!currentConn || !loadedDatasources.some(ds => ds.id === currentConn.id)) && loadedDatasources.length > 0) {
                    currentConn = loadedDatasources[0];
                    Store.set('currentConnection', currentConn);
                }
                if (currentConn?.id) {
                    this.datasourceSelector.setValue(currentConn.id);
                }
            },
            onChange: (datasource) => {
                if (!datasource) return;
                Store.set('currentConnection', datasource);
                this._loadSchemaForDatasource(datasource.id);
            }
        });

        const content = DOM.$('#page-content');
        content.innerHTML = '';
        const container = DOM.el('div', { className: 'query-container' });

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

        // Resizer between editor and results (appended at end, positioned via CSS order)
        const resizer = DOM.el('div', { className: 'query-resizer', id: 'query-resizer' });
        resizer.addEventListener('mousedown', (e) => this._startResize(e));

        QueryEditor.create(container, 'SELECT 1;');
        QueryEditor.onExecute = () => this._executeQuery();

        setTimeout(() => {
            const connId = this._getSelectedDatasourceId();
            if (connId) {
                this._loadSchemaForDatasource(connId);
            }
        }, 500);

        const statusBar = DOM.el('div', { className: 'query-status-bar', id: 'query-status' });
        statusBar.innerHTML = '<div class="status-info"><span class="text-muted">就绪</span></div>';
        container.appendChild(statusBar);

        const results = DOM.el('div', { className: 'query-results', id: 'query-results' });
        results.innerHTML = `
            <div class="empty-state" style="padding:40px">
                <i data-lucide="table"></i>
                <h3>暂无结果</h3>
                <p>执行查询后结果将显示在这里</p>
            </div>
        `;
        container.appendChild(resizer);
        container.appendChild(results);

        content.appendChild(container);
        DOM.createIcons();

        return () => {
            this.datasourceSelector?.destroy();
            this.datasourceSelector = null;
            this._cancelQuery();
            QueryEditor.destroy();
            DataTable.destroy();
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
        const connId = this._getSelectedDatasourceId();
        if (!connId) {
            Toast.warning('请先选择数据源');
            return;
        }

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
        const selectedSql = QueryEditor.getSelectedText();
        const sql = (selectedSql || QueryEditor.getValue()).trim();

        if (!sql) {
            Toast.warning('请输入 SQL 查询');
            return;
        }

        const connId = this._getSelectedDatasourceId();
        if (!connId) {
            Toast.warning('请先选择数据源');
            return;
        }

        const status = DOM.$('#query-status');
        const results = DOM.$('#query-results');
        const executeBtn = DOM.$('#execute-btn');
        const cancelBtn = DOM.$('#cancel-btn');

        if (!results || !status || !executeBtn || !cancelBtn) return;

        status.innerHTML = '<div class="status-info"><span><div class="spinner" style="display:inline-block;width:14px;height:14px;margin-right:8px"></div>执行中...</span></div>';
        results.innerHTML = '';
        executeBtn.disabled = true;
        cancelBtn.style.display = 'inline-flex';

        this.currentAbortController = new AbortController();

        try {
            const result = await API.executeQuery(
                { datasource_id: connId, sql, max_rows: 10000 },
                { signal: this.currentAbortController.signal }
            );

            if (result.columns && result.columns.length > 0) {
                const freshResults = DOM.$('#query-results');
                if (freshResults) {
                    freshResults.innerHTML = '';
                    try {
                        freshResults.appendChild(DataTable.create(result.columns, result.rows));
                    } catch (err) {
                        console.error('[Query] DataTable.create failed:', err);
                        freshResults.innerHTML = `<div style="padding:20px;color:var(--accent-red)">表格渲染失败</div>`;
                    }
                }
            } else if (result.message) {
                const freshResults = DOM.$('#query-results');
                if (freshResults) freshResults.innerHTML = `<div class="empty-state" style="padding:20px"><p>${result.message}</p></div>`;
            }

            if (status.parentNode) {
                const statusText = `${result.row_count} 行 | ${result.execution_time_ms}ms${result.truncated ? ' | 已截断至10000行' : ''}`;
                status.innerHTML = `<div class="status-info"><span style="color:var(--accent-green)">${statusText}</span></div>`;
            }
        } catch (err) {
            if (err.name === 'AbortError') {
                return;
            }
            const errResults = DOM.$('#query-results');
            if (errResults) {
                errResults.innerHTML = `<div style="padding:20px;color:var(--accent-red);font-family:var(--font-mono);font-size:13px;white-space:pre-wrap">${err.message}</div>`;
            }
            const errStatus = DOM.$('#query-status');
            if (errStatus) {
                errStatus.innerHTML = '<div class="status-info"><span style="color:var(--accent-red)">错误</span></div>';
            }
        } finally {
            this.currentAbortController = null;
            if (executeBtn) executeBtn.disabled = false;
            if (cancelBtn) cancelBtn.style.display = 'none';
        }
    },

    async _explainQuery() {
        const selectedSql = QueryEditor.getSelectedText();
        const sql = (selectedSql || QueryEditor.getValue()).trim();

        if (!sql) {
            Toast.warning('请输入 SQL 查询');
            return;
        }

        const connId = this._getSelectedDatasourceId();
        if (!connId) {
            Toast.warning('请先选择数据源');
            return;
        }

        const results = DOM.$('#query-results');
        if (!results) return;
        results.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const result = await API.explainQuery({ datasource_id: connId, sql });
            const freshResults = DOM.$('#query-results');
            if (!freshResults) return;
            freshResults.innerHTML = '';

            if (result.columns && result.rows) {
                try {
                    freshResults.appendChild(DataTable.create(result.columns, result.rows));
                } catch (err) {
                    console.error('[Query] DataTable.create failed:', err);
                    freshResults.innerHTML = `<div style="padding:20px;color:var(--accent-red)">表格渲染失败</div>`;
                }
            } else if (result.plan) {
                const pre = DOM.el('div', { className: 'explain-panel', textContent: JSON.stringify(result.plan, null, 2) });
                freshResults.appendChild(pre);
            } else {
                const pre = DOM.el('div', { className: 'explain-panel', textContent: JSON.stringify(result, null, 2) });
                freshResults.appendChild(pre);
                results.appendChild(pre);
            }
        } catch (err) {
            results.innerHTML = `<div style="padding:20px;color:var(--accent-red)">${err.message}</div>`;
        }
    },

    _startResize(e) {
        this.isResizing = true;
        this.startY = e.clientY;
        const wrapper = DOM.$('.query-editor-wrapper');
        this.startHeight = wrapper ? wrapper.offsetHeight : 400;
        document.body.style.cursor = 'row-resize';
        document.body.style.userSelect = 'none';
        const resizer = DOM.$('#query-resizer');
        if (resizer) resizer.classList.add('dragging');

        const onMouseMove = (e) => {
            if (!this.isResizing) return;
            const delta = e.clientY - this.startY;
            const newHeight = Math.max(100, Math.min(this.startHeight + delta, window.innerHeight - 200));
            QueryEditor.setHeight(newHeight);
        };

        const onMouseUp = () => {
            this.isResizing = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            const resizer = DOM.$('#query-resizer');
            if (resizer) resizer.classList.remove('dragging');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
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
