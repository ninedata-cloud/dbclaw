/* SQL Console page */
const SqlConsolePage = {
    sqlDraftStoragePrefix: 'dbclaw:sql-console:draft:',
    sqlDraftTtlMs: 30 * 24 * 60 * 60 * 1000,
    currentAbortController: null,
    currentQueryRequestId: null,
    currentQueryDatasourceId: null,
    datasourceSelector: null,
    _renderOptions: null,
    _container: null,
    currentDatabase: null,
    currentSchema: null,
    currentDbType: null,
    supportsDatabase: false,
    supportsSchema: false,
    databaseOptions: [],
    schemaOptions: [],
    editorHeight: 320,
    resizeHandler: null,
    isResizing: false,
    startY: 0,
    startHeight: 0,
    beforeUnloadHandler: null,

    _getSelectedDatasource() {
        return this.datasourceSelector?.getValue() || Store.get('currentConnection') || null;
    },

    _getSelectedDatasourceId() {
        return this._getSelectedDatasource()?.id || null;
    },

    _getDraftStorageKey(datasource = null) {
        const target = datasource || this._getSelectedDatasource();
        if (!target || !target.id) return null;
        const host = String(target.host || '').trim().toLowerCase();
        const port = String(target.port || '').trim();
        const serviceAddress = port ? `${host}:${port}` : host;
        const username = String(target.username || '').trim().toLowerCase();
        const identity = [
            serviceAddress || '-',
            username || '-',
            String(target.id)
        ].join('|');
        return `${this.sqlDraftStoragePrefix}${encodeURIComponent(identity)}`;
    },

    _readSqlDraft(datasource = null) {
        const key = this._getDraftStorageKey(datasource);
        if (!key) return null;
        try {
            const raw = window.localStorage.getItem(key);
            if (!raw) return null;
            const payload = JSON.parse(raw);
            if (!payload || typeof payload !== 'object') {
                window.localStorage.removeItem(key);
                return null;
            }
            const expiresAt = Number(payload.expiresAt || 0);
            if (!expiresAt || Date.now() > expiresAt) {
                window.localStorage.removeItem(key);
                return null;
            }
            return typeof payload.sql === 'string' ? payload.sql : null;
        } catch (error) {
            console.warn('[SqlConsole] Failed to read SQL draft:', error);
            return null;
        }
    },

    _saveSqlDraft(datasource = null) {
        const key = this._getDraftStorageKey(datasource);
        if (!key) return;
        const sql = QueryEditor.getValue();
        if (typeof sql !== 'string') return;
        const now = Date.now();
        const payload = {
            sql,
            savedAt: now,
            expiresAt: now + this.sqlDraftTtlMs,
        };
        try {
            window.localStorage.setItem(key, JSON.stringify(payload));
        } catch (error) {
            console.warn('[SqlConsole] Failed to persist SQL draft:', error);
        }
    },

    _applySqlDraftForDatasource(datasource = null) {
        const draftSql = this._readSqlDraft(datasource);
        QueryEditor.setValue(draftSql ?? 'SELECT 1;');
    },

    async render() {
        return this.renderWithOptions({});
    },

    async renderWithOptions(options = {}) {
        this._renderOptions = options || {};
        const content = options.container || DOM.$('#page-content');
        this._container = content;

        let datasources = Store.get('datasources') || [];
        if (datasources.length === 0) {
            try {
                datasources = await API.getDatasources();
                Store.set('datasources', datasources);
            } catch (e) {
                console.error('[SqlConsole] Failed to load datasources:', e);
            }
        }

        let currentConn = null;
        if (options.fixedDatasourceId) {
            currentConn = datasources.find(ds => ds.id === options.fixedDatasourceId) || null;
        } else {
            currentConn = Store.get('currentConnection');
        }
        if (!currentConn && datasources.length > 0) {
            currentConn = datasources[0];
        }
        if (currentConn) {
            Store.set('currentConnection', currentConn);
        }
        const initialSql = this._readSqlDraft(currentConn) ?? 'SELECT 1;';

        const headerActions = DOM.el('div', { className: 'flex gap-8', style: { flex: '1', minWidth: '0' } });
        this.datasourceSelector?.destroy();
        this.datasourceSelector = null;
        if (!options.fixedDatasourceId) {
            const datasourceContainer = DOM.el('div', {
                id: 'query-datasource-selector',
                style: { minWidth: '280px', maxWidth: '380px', flex: '1' }
            });
            headerActions.appendChild(datasourceContainer);
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
                    currentConn = datasource;
                    this.currentDatabase = null;
                    this.currentSchema = null;
                    this._applySqlDraftForDatasource(datasource);
                    this._loadQueryContext(datasource.id, { resetSelections: true });
                }
            });
        }

        content.innerHTML = '';
        if (!options.embedded) {
            Header.render('SQL 窗口', headerActions);
        }
        const container = DOM.el('div', { className: 'sql-console-container' });
        const toolbar = DOM.el('div', { className: 'sql-console-toolbar' });
        const toolbarActions = DOM.el('div', { className: 'sql-console-toolbar-main-actions' });
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
        const diagnoseBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="sparkles"></i> 诊断优化',
            onClick: () => this._diagnoseSql()
        });
        const historyBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="history"></i> 历史记录',
            onClick: () => this._showHistory()
        });
        toolbarActions.appendChild(executeBtn);
        toolbarActions.appendChild(cancelBtn);
        toolbarActions.appendChild(explainBtn);
        toolbarActions.appendChild(diagnoseBtn);
        toolbarActions.appendChild(historyBtn);
        toolbar.appendChild(toolbarActions);

        const contextToolbar = DOM.el('div', { className: 'sql-console-toolbar-context', id: 'sql-console-context-toolbar' });
        contextToolbar.innerHTML = `
            <div class="sql-console-context-group" id="sql-console-database-group">
                <label for="sql-console-database-select">数据库</label>
                <select id="sql-console-database-select" class="form-select">
                    <option value="">加载中...</option>
                </select>
            </div>
            <div class="sql-console-context-group" id="sql-console-schema-group" style="display:none;">
                <label for="sql-console-schema-select">Schema</label>
                <select id="sql-console-schema-select" class="form-select">
                    <option value="">默认</option>
                </select>
            </div>
        `;
        toolbar.appendChild(contextToolbar);
        container.appendChild(toolbar);

        // Resizer between editor and results (appended at end, positioned via CSS order)
        const resizer = DOM.el('div', { className: 'sql-console-resizer', id: 'sql-console-resizer' });
        resizer.addEventListener('mousedown', (e) => this._startResize(e));

        QueryEditor.create(container, initialSql);
        QueryEditor.onExecute = () => this._executeQuery();

        if (this.beforeUnloadHandler) {
            window.removeEventListener('beforeunload', this.beforeUnloadHandler);
        }
        this.beforeUnloadHandler = () => this._saveSqlDraft();
        window.addEventListener('beforeunload', this.beforeUnloadHandler);

        setTimeout(() => {
            const connId = this._getSelectedDatasourceId();
            if (connId) {
                this._loadQueryContext(connId, { resetSelections: true });
            }
        }, 500);

        const results = DOM.el('div', { className: 'sql-console-results', id: 'sql-console-results' });
        results.innerHTML = `
            <div class="empty-state" style="padding:40px">
                <i data-lucide="table"></i>
                <h3>暂无结果</h3>
                <p>执行查询后结果将显示在这里</p>
            </div>
        `;
        container.appendChild(resizer);
        container.appendChild(results);
        const statusBar = DOM.el('div', { className: 'sql-console-status-bar', id: 'sql-console-status' });
        statusBar.innerHTML = '<div class="status-info"><span class="text-muted">就绪</span></div>';
        container.appendChild(statusBar);
        
        content.appendChild(container);
        DOM.createIcons();
        this._bindResizeHandler();
        requestAnimationFrame(() => this._applyAdaptiveEditorHeight());

        return () => {
            if (this.resizeHandler) {
                window.removeEventListener('resize', this.resizeHandler);
                this.resizeHandler = null;
            }
            this._saveSqlDraft();
            if (this.beforeUnloadHandler) {
                window.removeEventListener('beforeunload', this.beforeUnloadHandler);
                this.beforeUnloadHandler = null;
            }
            this.datasourceSelector?.destroy();
            this.datasourceSelector = null;
            this._cancelQuery();
            QueryEditor.destroy();
            DataTable.destroy();
            this.currentDatabase = null;
            this.currentSchema = null;
            this.currentDbType = null;
            this.supportsDatabase = false;
            this.supportsSchema = false;
            this.databaseOptions = [];
            this.schemaOptions = [];
            this._renderOptions = null;
            this._container = null;
            this.currentQueryRequestId = null;
            this.currentQueryDatasourceId = null;
        };
    },

    _generateRequestId() {
        if (window.crypto?.randomUUID) {
            return window.crypto.randomUUID();
        }
        return `sql-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    },

    _getCurrentExecutionContext() {
        const databaseSelect = DOM.$('#sql-console-database-select');
        const schemaSelect = DOM.$('#sql-console-schema-select');

        if (databaseSelect) {
            this.currentDatabase = this._normalizeContextValue(databaseSelect.value);
        }
        if (schemaSelect && this.supportsSchema) {
            this.currentSchema = this._normalizeContextValue(schemaSelect.value);
        }

        return {
            database: this.currentDatabase || null,
            schema: this.supportsSchema ? (this.currentSchema || null) : null,
        };
    },

    _normalizeContextValue(value) {
        if (value === null || value === undefined) {
            return null;
        }
        const normalized = String(value).trim();
        return normalized || null;
    },

    _buildSelectOptions(selectElement, values, selectedValue, defaultLabel) {
        if (!selectElement) return;
        const normalizedValues = Array.isArray(values)
            ? values.filter(value => value !== undefined && value !== null && String(value).trim() !== '')
            : [];
        const currentValue = this._normalizeContextValue(selectedValue);
        const options = [...normalizedValues];

        if (currentValue && !options.includes(currentValue)) {
            options.unshift(currentValue);
        }

        if (options.length === 0) {
            options.push('');
        }

        selectElement.innerHTML = '';
        options.forEach((item) => {
            const option = document.createElement('option');
            option.value = item;
            option.textContent = item || defaultLabel;
            option.selected = item === currentValue || (!item && !currentValue);
            selectElement.appendChild(option);
        });
    },

    _resolveSelection(requestedValue, fallbackValue, availableValues = []) {
        const normalizedRequested = this._normalizeContextValue(requestedValue);
        const normalizedFallback = this._normalizeContextValue(fallbackValue);

        if (normalizedRequested) {
            return normalizedRequested;
        }
        if (normalizedFallback && availableValues.includes(normalizedFallback)) {
            return normalizedFallback;
        }
        if (normalizedFallback && availableValues.length === 0) {
            return normalizedFallback;
        }
        return availableValues[0] || null;
    },

    _renderQueryContextSelectors() {
        const contextToolbar = DOM.$('#sql-console-context-toolbar');
        const databaseGroup = DOM.$('#sql-console-database-group');
        const databaseSelect = DOM.$('#sql-console-database-select');
        const schemaSelect = DOM.$('#sql-console-schema-select');
        const schemaGroup = DOM.$('#sql-console-schema-group');

        if (contextToolbar) {
            contextToolbar.style.display = (this.supportsDatabase || this.supportsSchema) ? 'flex' : 'none';
        }

        if (databaseGroup) {
            databaseGroup.style.display = this.supportsDatabase ? '' : 'none';
        }

        if (databaseSelect) {
            this._buildSelectOptions(databaseSelect, this.databaseOptions, this.currentDatabase, '默认数据库');
            databaseSelect.onchange = async (event) => {
                this.currentDatabase = this._normalizeContextValue(event.target.value);
                this.currentSchema = null;
                const datasourceId = this._getSelectedDatasourceId();
                if (datasourceId) {
                    await this._loadQueryContext(datasourceId, {
                        database: this.currentDatabase,
                        schema: null,
                    });
                }
            };
        }

        if (schemaGroup) {
            schemaGroup.style.display = this.supportsSchema ? '' : 'none';
        }

        if (schemaSelect && this.supportsSchema) {
            this._buildSelectOptions(schemaSelect, this.schemaOptions, this.currentSchema, '默认 Schema');
            schemaSelect.onchange = async (event) => {
                this.currentSchema = this._normalizeContextValue(event.target.value);
                const datasourceId = this._getSelectedDatasourceId();
                if (datasourceId) {
                    await this._loadSchemaForDatasource(datasourceId);
                }
            };
        }
    },

    async _loadQueryContext(datasourceId, options = {}) {
        const requestedDatabase = Object.prototype.hasOwnProperty.call(options, 'database')
            ? (options.database || null)
            : (options.resetSelections ? null : this.currentDatabase);
        const requestedSchema = Object.prototype.hasOwnProperty.call(options, 'schema')
            ? (options.schema || null)
            : (options.resetSelections ? null : this.currentSchema);

        try {
            const context = await API.getQueryContext(datasourceId, requestedDatabase);
            this.currentDbType = context.db_type || null;
            this.supportsDatabase = Boolean(context.supports_database) && (context.databases || []).length > 0;
            this.databaseOptions = context.databases || [];
            this.supportsSchema = Boolean(context.supports_schema);
            this.schemaOptions = context.schemas || [];
            this.currentDatabase = this._resolveSelection(
                requestedDatabase,
                context.current_database,
                this.databaseOptions
            );
            this.currentSchema = this.supportsSchema
                ? this._resolveSelection(
                    requestedSchema,
                    context.current_schema,
                    this.schemaOptions
                )
                : null;
        } catch (error) {
            console.error('[SqlConsole] Failed to load query context:', error);
            this.currentDbType = null;
            this.supportsDatabase = false;
            this.databaseOptions = [];
            this.schemaOptions = [];
            this.supportsSchema = false;
            this.currentDatabase = null;
            this.currentSchema = null;
        }

        this._renderQueryContextSelectors();
        await this._loadSchemaForDatasource(datasourceId);
    },

    async _loadSchemaForDatasource(datasourceId) {
        try {
            await QueryEditor.setSchema(datasourceId, this._getCurrentExecutionContext());
        } catch (error) {
            console.error('Error loading schema:', error);
        }
    },

    _cancelQuery() {
        const abortController = this.currentAbortController;
        const requestId = this.currentQueryRequestId;
        const datasourceId = this.currentQueryDatasourceId;

        if (requestId && datasourceId) {
            API.cancelQuery(
                { datasource_id: datasourceId, request_id: requestId },
                { keepalive: true }
            ).catch((error) => {
                console.warn('[SqlConsole] Failed to cancel query on server:', error);
                Toast.warning(error.message || '取消请求发送失败，后端 SQL 可能仍在执行');
            });
        }

        if (abortController || requestId) {
            this.currentAbortController = null;
            this.currentQueryRequestId = null;
            this.currentQueryDatasourceId = null;

            if (abortController) {
                abortController.abort();
            }

            const status = DOM.$('#sql-console-status');
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

    _bindResizeHandler() {
        if (this.resizeHandler) {
            window.removeEventListener('resize', this.resizeHandler);
        }

        this.resizeHandler = () => this._applyAdaptiveEditorHeight();
        window.addEventListener('resize', this.resizeHandler);
    },

    _getEditorHeightBounds() {
        const container = DOM.$('.sql-console-container');
        const toolbar = DOM.$('.sql-console-toolbar');
        const resizer = DOM.$('#sql-console-resizer');
        const statusBar = DOM.$('#sql-console-status');
        const minEditorHeight = 0;
        const preferredResultsHeight = 140;

        if (!container) {
            return { min: minEditorHeight, max: this.editorHeight || 400 };
        }

        const reservedHeight = [toolbar, resizer, statusBar]
            .reduce((total, element) => total + (element?.offsetHeight || 0), 0);
        const availableHeight = Math.max(0, container.clientHeight - reservedHeight);
        const maxEditorHeight = Math.max(minEditorHeight, availableHeight - preferredResultsHeight);

        return {
            min: minEditorHeight,
            max: maxEditorHeight,
        };
    },

    _applyAdaptiveEditorHeight() {
        const wrapper = DOM.$('.sql-console-editor-wrapper');
        if (!wrapper) return;

        const { min, max } = this._getEditorHeightBounds();
        const currentHeight = wrapper.offsetHeight || this.editorHeight || 400;
        const nextHeight = Math.max(min, Math.min(currentHeight, max));

        wrapper.style.height = `${nextHeight}px`;
        this.editorHeight = nextHeight;
    },

    async _executeQuery() {
        const selectedSql = QueryEditor.getSelectedText();
        const sql = (selectedSql || QueryEditor.getValue()).trim();

        if (!sql) {
            Toast.warning('请输入 SQL 语句');
            return;
        }

        const connId = this._getSelectedDatasourceId();
        if (!connId) {
            Toast.warning('请先选择数据源');
            return;
        }
        this._saveSqlDraft();

        const status = DOM.$('#sql-console-status');
        const results = DOM.$('#sql-console-results');
        const executeBtn = DOM.$('#execute-btn');
        const cancelBtn = DOM.$('#cancel-btn');

        if (!results || !status || !executeBtn || !cancelBtn) return;

        status.innerHTML = '<div class="status-info"><span><div class="spinner" style="display:inline-block;width:14px;height:14px;margin-right:8px"></div>执行中...</span></div>';
        results.innerHTML = '';
        executeBtn.disabled = true;
        cancelBtn.style.display = 'inline-flex';

        const requestId = this._generateRequestId();
        const abortController = new AbortController();
        this.currentAbortController = abortController;
        this.currentQueryRequestId = requestId;
        this.currentQueryDatasourceId = connId;

        try {
            const result = await API.executeQuery(
                { datasource_id: connId, request_id: requestId, sql, max_rows: 10000, ...this._getCurrentExecutionContext() },
                { signal: abortController.signal }
            );

            if (result.columns && result.columns.length > 0) {
                const freshResults = DOM.$('#sql-console-results');
                if (freshResults) {
                    freshResults.innerHTML = '';
                    try {
                        freshResults.appendChild(DataTable.create(result.columns, result.rows));
                    } catch (err) {
                        console.error('[SqlConsole] DataTable.create failed:', err);
                        freshResults.innerHTML = `<div style="padding:20px;color:var(--accent-red)">表格渲染失败</div>`;
                    }
                }
            } else if (result.message) {
                const freshResults = DOM.$('#sql-console-results');
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
            if (err.message === '查询已取消') {
                const canceledStatus = DOM.$('#sql-console-status');
                if (canceledStatus) {
                    canceledStatus.innerHTML = '<div class="status-info"><span style="color:var(--accent-orange)">已取消</span></div>';
                }
                return;
            }
            const errResults = DOM.$('#sql-console-results');
            if (errResults) {
                errResults.innerHTML = `<div style="padding:20px;color:var(--accent-red);font-family:var(--font-mono);font-size:13px;white-space:pre-wrap">${err.message}</div>`;
            }
            const errStatus = DOM.$('#sql-console-status');
            if (errStatus) {
                errStatus.innerHTML = '<div class="status-info"><span style="color:var(--accent-red)">错误</span></div>';
            }
        } finally {
            if (this.currentQueryRequestId === requestId) {
                this.currentAbortController = null;
                this.currentQueryRequestId = null;
                this.currentQueryDatasourceId = null;
                if (executeBtn) executeBtn.disabled = false;
                if (cancelBtn) cancelBtn.style.display = 'none';
            }
        }
    },

    async _explainQuery() {
        const selectedSql = QueryEditor.getSelectedText();
        const sql = (selectedSql || QueryEditor.getValue()).trim();

        if (!sql) {
            Toast.warning('请输入 SQL 语句');
            return;
        }

        const connId = this._getSelectedDatasourceId();
        if (!connId) {
            Toast.warning('请先选择数据源');
            return;
        }

        const results = DOM.$('#sql-console-results');
        if (!results) return;
        results.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const result = await API.explainQuery({ datasource_id: connId, sql, ...this._getCurrentExecutionContext() });
            const freshResults = DOM.$('#sql-console-results');
            if (!freshResults) return;
            freshResults.innerHTML = '';

            if (result.columns && result.rows) {
                try {
                    freshResults.appendChild(DataTable.create(result.columns, result.rows));
                } catch (err) {
                    console.error('[SqlConsole] DataTable.create failed:', err);
                    freshResults.innerHTML = `<div style="padding:20px;color:var(--accent-red)">表格渲染失败</div>`;
                }
            } else if (result.plan) {
                const pre = DOM.el('div', { className: 'explain-panel', textContent: JSON.stringify(result.plan, null, 2) });
                freshResults.appendChild(pre);
            } else {
                const pre = DOM.el('div', { className: 'explain-panel', textContent: JSON.stringify(result, null, 2) });
                freshResults.appendChild(pre);
            }
        } catch (err) {
            results.innerHTML = `<div style="padding:20px;color:var(--accent-red)">${err.message}</div>`;
        }
    },

    _startResize(e) {
        e.preventDefault();
        this.isResizing = true;
        this.startY = e.clientY;
        const wrapper = DOM.$('.sql-console-editor-wrapper');
        this.startHeight = wrapper ? wrapper.offsetHeight : 400;

        document.body.style.cursor = 'row-resize';
        document.body.style.userSelect = 'none';
        const resizer = DOM.$('#sql-console-resizer');
        if (resizer) resizer.classList.add('dragging');

        const onMouseMove = (e) => {
            if (!this.isResizing) return;
            e.preventDefault();
            const delta = e.clientY - this.startY;
            const { min, max } = this._getEditorHeightBounds();
            const newHeight = Math.max(min, Math.min(this.startHeight + delta, max));

            const wrapper = DOM.$('.sql-console-editor-wrapper');
            if (wrapper) {
                wrapper.style.height = `${newHeight}px`;
                this.editorHeight = newHeight;
            }
        };

        const onMouseUp = () => {
            this.isResizing = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            const resizer = DOM.$('#sql-console-resizer');
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
            const datasourceId = this._renderOptions?.filterHistoryDatasourceId || this._getSelectedDatasourceId();
            const filteredHistory = datasourceId
                ? history.filter(item => Number(item.datasource_id) === Number(datasourceId))
                : history;
            const container = DOM.el('div');

            if (filteredHistory.length === 0) {
                container.innerHTML = '<p class="text-muted text-center">暂无查询历史</p>';
            } else {
                for (const item of filteredHistory.slice(0, 20)) {
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
    },

    _buildSqlDiagnosisPrompt(sql, datasource) {
        const dbTypeLabel = this._getDbTypeLabel(datasource?.db_type) || datasource?.db_type || '未知';
        const hostText = datasource?.host ? `${datasource.host}:${datasource.port || '-'}` : '-';
        const versionText = datasource?.db_version ? this._simplifyVersion(datasource.db_version, datasource.db_type).short : '-';
        const databaseText = this.currentDatabase || datasource?.database || '-';
        const schemaText = this.currentSchema || '-';

        return [
            '请你作为资深数据库性能优化专家，针对下面这条 SQL 语句进行诊断和优化分析，并支持后续多轮追问。',
            '',
            '【分析目标】',
            '1. 分析 SQL 语句的性能瓶颈和潜在问题',
            '2. 评估索引使用情况和优化建议',
            '3. 提供改写建议和最佳实践',
            '4. 给出具体的优化方案和预期效果',
            '',
            '【数据库信息】',
            `- 实例名称：${datasource?.name || '-'}`,
            `- 数据库类型：${dbTypeLabel}`,
            `- 主机：${hostText}`,
            `- 数据库：${databaseText}`,
            this.supportsSchema && schemaText !== '-' ? `- Schema：${schemaText}` : null,
            versionText !== '-' ? `- 版本：${versionText}` : null,
            '',
            '【待优化 SQL】',
            '```sql',
            sql,
            '```',
            '',
            '请从以下几个方面进行分析：',
            '1. SQL 语句结构分析（JOIN、子查询、聚合等）',
            '2. 可能的性能问题点',
            '3. 索引优化建议',
            '4. SQL 改写建议',
            '5. 其他优化建议',
        ].filter(line => line !== null).join('\n');
    },

    _getDbTypeLabel(dbType) {
        const labels = {
            'mysql': 'MySQL',
            'postgresql': 'PostgreSQL',
            'oracle': 'Oracle',
            'sqlserver': 'SQL Server',
            'mongodb': 'MongoDB',
            'redis': 'Redis',
            'clickhouse': 'ClickHouse',
            'tidb': 'TiDB',
            'oceanbase': 'OceanBase',
            'dameng': '达梦',
            'kingbase': '人大金仓',
            'gbase': 'GBase',
            'hana': 'SAP HANA'
        };
        return labels[dbType] || null;
    },

    async _diagnoseSql() {
        const selectedSql = QueryEditor.getSelectedText();
        const sql = (selectedSql || QueryEditor.getValue()).trim();

        if (!sql) {
            Toast.warning('请输入或选择要诊断的 SQL 语句');
            return;
        }

        const datasource = this._getSelectedDatasource();
        if (!datasource) {
            Toast.warning('请先选择数据源');
            return;
        }

        let dialogCleanup = null;
        const content = DOM.el('div', { className: 'instance-session-ai-shell' });
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        const title = `SQL 诊断优化 · ${datasource.name || '实例'}`;

        Modal.show({
            title,
            content,
            width: '1280px',
            maxHeight: '92vh',
            containerClassName: 'instance-session-ai-modal',
            bodyClassName: 'instance-session-ai-modal-body',
            onHide: () => {
                if (typeof dialogCleanup === 'function') {
                    try {
                        dialogCleanup();
                    } catch (error) {
                        console.error('SQL diagnosis dialog cleanup failed:', error);
                    }
                }
            }
        });

        try {
            dialogCleanup = await DiagnosisPage.renderWithOptions({
                container: content,
                embedded: true,
                hideEmbeddedTitle: true,
                compactEmbeddedToolbar: true,
                fixedDatasourceId: datasource.id,
                hideSessionSidebar: true,
                autoCreateSession: true,
                autoSendInitialAsk: true,
                hideInitialAskMessage: true,
                initialAsk: this._buildSqlDiagnosisPrompt(sql, datasource),
                initialSessionTitle: `SQL 诊断优化 ${datasource.name || datasource.id || ''}`.trim(),
                hideToolSafetyButton: true,
                hideClearSessionButton: true,
            });
        } catch (error) {
            content.innerHTML = `
                <div class="empty-state" style="padding:40px;">
                    <i data-lucide="alert-circle"></i>
                    <h3>SQL 诊断优化打开失败</h3>
                    <p>${error.message || '未知错误'}</p>
                </div>
            `;
            DOM.createIcons();
        }
    },

    _simplifyVersion(fullVersion, dbType) {
        if (!fullVersion) return { short: '未知版本', full: '', details: '' };

        const patterns = {
            'postgresql': /PostgreSQL\s+([\d.]+)/i,
            'mysql': /([\d.]+)/,
            'oracle': /Oracle Database ([\d.]+)/i,
            'sqlserver': /Microsoft SQL Server\s+([\d.]+)/i,
            'opengauss': /openGauss\s+([\d.]+)/i,
            'hana': /HDB\s+([\d.]+)/i,
            'tdsql': /([\d.]+)/
        };

        const dbTypeNormalized = (dbType || '').toLowerCase().replace(/[_-]/g, '');
        const pattern = patterns[dbTypeNormalized];

        if (pattern) {
            const match = fullVersion.match(pattern);
            if (match) {
                const versionNum = match[1];
                const dbDisplayNames = {
                    'postgresql': 'PostgreSQL',
                    'mysql': 'MySQL',
                    'oracle': 'Oracle',
                    'sqlserver': 'SQL Server',
                    'opengauss': 'openGauss',
                    'hana': 'SAP HANA',
                    'tdsql': 'TDSQL-C'
                };
                const displayName = dbDisplayNames[dbTypeNormalized] || dbType.toUpperCase();
                const short = `${displayName} ${versionNum}`;
                const details = fullVersion.substring(match.index + match[0].length).trim().replace(/^[,\s]+/, '');

                return { short, full: fullVersion, details };
            }
        }

        if (fullVersion.length > 50) {
            return {
                short: fullVersion.substring(0, 50) + '...',
                full: fullVersion,
                details: fullVersion.substring(50)
            };
        }

        return { short: fullVersion, full: fullVersion, details: '' };
    }
};
