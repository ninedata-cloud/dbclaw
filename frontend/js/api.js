/* API fetch wrapper */
const AUTH_STATE_KEY = 'dbclaw_has_session';

const API = {
    markSessionAvailable() {
        try {
            localStorage.setItem(AUTH_STATE_KEY, '1');
        } catch (e) {
            // ignore localStorage errors
        }
    },

    clearSessionMark() {
        try {
            localStorage.removeItem(AUTH_STATE_KEY);
        } catch (e) {
            // ignore localStorage errors
        }
    },

    shouldRestoreSession() {
        try {
            return localStorage.getItem(AUTH_STATE_KEY) === '1';
        } catch (e) {
            return false;
        }
    },

    async request(url, options = {}) {
        const defaultOpts = {
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
        };
        const merged = { ...defaultOpts, ...options };
        merged.headers = { ...defaultOpts.headers, ...(options.headers || {}) };

        if (merged.body && typeof merged.body === 'object' && !(merged.body instanceof FormData)) {
            merged.body = JSON.stringify(merged.body);
        }
        try {
            const response = await fetch(url, merged);
            if (!response.ok) {
                if (response.status === 401 && url !== '/api/auth/login') {
                    Store.set('currentUser', null);
                    this.clearSessionMark();
                    window.location.hash = 'login';
                    throw new Error('会话已过期，请重新登录');
                }

                const err = await response.json().catch(() => ({ detail: response.statusText }));

                let errorMessage = '请求失败';

                if (err.detail) {
                    if (typeof err.detail === 'string') {
                        errorMessage = err.detail;
                    } else if (Array.isArray(err.detail)) {
                        errorMessage = err.detail.map(e => {
                            const loc = e.loc ? e.loc.join('.') : '';
                            return `${loc}: ${e.msg}`;
                        }).join('; ');
                    } else if (typeof err.detail === 'object') {
                        errorMessage = JSON.stringify(err.detail);
                    }
                } else if (err.message) {
                    errorMessage = typeof err.message === 'string' ? err.message : JSON.stringify(err.message);
                }

                throw new Error(errorMessage);
            }
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }
            return await response.text();
        } catch (error) {
            throw error;
        }
    },

    get(url) { return this.request(url); },
    post(url, body) { return this.request(url, { method: 'POST', body }); },
    put(url, body) { return this.request(url, { method: 'PUT', body }); },
    delete(url) { return this.request(url, { method: 'DELETE' }); },

    getAppInfo() { return this.get('/api/app/info'); },

    async postFormData(url, formData) {
        const response = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            body: formData
        });
        if (!response.ok) {
            if (response.status === 401) {
                Store.set('currentUser', null);
                this.clearSessionMark();
                window.location.hash = 'login';
                throw new Error('会话已过期，请重新登录');
            }

            const err = await response.json().catch(() => ({ detail: response.statusText }));

            let errorMessage = '请求失败';

            if (err.detail) {
                if (typeof err.detail === 'string') {
                    errorMessage = err.detail;
                } else if (Array.isArray(err.detail)) {
                    errorMessage = err.detail.map(e => {
                        const loc = e.loc ? e.loc.join('.') : '';
                        return `${loc}: ${e.msg}`;
                    }).join('; ');
                } else if (typeof err.detail === 'object') {
                    errorMessage = JSON.stringify(err.detail);
                }
            } else if (err.message) {
                errorMessage = typeof err.message === 'string' ? err.message : JSON.stringify(err.message);
            }

            throw new Error(errorMessage);
        }
        return await response.json();
    },

    login(username, password) { return this.post('/api/auth/login', { username, password }); },
    getMe() { return this.get('/api/auth/me'); },
    updateMe(data) { return this.put('/api/auth/me', data); },
    logout() { return this.post('/api/auth/logout', {}); },
    logoutAll() { return this.post('/api/auth/logout-all', {}); },
    changePassword(old_password, new_password) { return this.post('/api/auth/change-password', { old_password, new_password }); },

    // User endpoints
    getUsers() { return this.get('/api/users'); },
    createUser(data) { return this.post('/api/users', data); },
    updateUser(id, data) { return this.put(`/api/users/${id}`, data); },
    deleteUser(id) { return this.delete(`/api/users/${id}`); },
    resetUserPassword(id, new_password) { return this.post(`/api/users/${id}/reset-password`, { new_password }); },
    toggleUserStatus(id) { return this.post(`/api/users/${id}/toggle-status`); },
    getUserLoginLogs(id) { return this.get(`/api/users/${id}/login-logs`); },

    // Datasource endpoints
    getDatasources(params = null) {
        const queryString = params ? `?${new URLSearchParams(params).toString()}` : '';
        return this.get(`/api/datasources${queryString}`);
    },
    createDatasource(data) { return this.post('/api/datasources', data); },
    updateDatasource(id, data) { return this.put(`/api/datasources/${id}`, data); },
    deleteDatasource(id) { return this.delete(`/api/datasources/${id}`); },
    testDatasource(id) { return this.post(`/api/datasources/${id}/test`); },
    testDatasourceConnection(data) { return this.post('/api/datasources/test', data); },
    checkDatasourceStatus() { return this.post('/api/datasources/check-status'); },

    // Datasource silence endpoints
    setDatasourceSilence(id, data) { return this.post(`/api/datasources/${id}/silence`, data); },
    cancelDatasourceSilence(id) { return this.delete(`/api/datasources/${id}/silence`); },
    getDatasourceSilenceStatus(id) { return this.get(`/api/datasources/${id}/silence`); },

    // Bulk status check for datasources
    checkAllDatasourceStatus() { return this.post('/api/datasources/check-status'); },

    // Get latest metrics for all datasources (lightweight)
    getDatasourcesLatestMetrics() { return this.get('/api/datasources/latest-metrics'); },

    // Host endpoints
    getHosts() { return this.get('/api/hosts'); },
    createHost(data) { return this.post('/api/hosts', data); },
    updateHost(id, data) { return this.put(`/api/hosts/${id}`, data); },
    deleteHost(id) { return this.delete(`/api/hosts/${id}`); },
    testHostConnection(data) { return this.post('/api/hosts/test', data); },
    testHost(id) { return this.post(`/api/hosts/${id}/test`); },

    // Host detail endpoints
    getHostSummary(hostId) { return this.get(`/api/host-detail/${hostId}/summary`); },
    getHostMetrics(hostId, params = '') { return this.get(`/api/host-detail/${hostId}/metrics${params ? '?' + params : ''}`); },
    getHostProcesses(hostId) { return this.get(`/api/hosts/${hostId}/processes`); },
    getProcessDetail(hostId, pid) { return this.get(`/api/hosts/${hostId}/processes/${pid}`); },
    killHostProcess(hostId, pid) { return this.post(`/api/host-detail/${hostId}/processes/${pid}/kill`); },
    getHostConnections(hostId) { return this.get(`/api/host-detail/${hostId}/connections`); },
    getHostNetworkTopology(hostId) { return this.get(`/api/host-detail/${hostId}/network-topology`); },
    getHostConfig(hostId) { return this.get(`/api/host-detail/${hostId}/config`); },
    refreshHostConfig(hostId) { return this.post(`/api/host-detail/${hostId}/config/refresh`); },

    // Metrics endpoints
    getMetrics(connId, params = '') { return this.get(`/api/metrics/${connId}${params ? '?' + params : ''}`); },
    getLatestMetric(connId, type = 'db_status') { return this.get(`/api/metrics/${connId}/latest?metric_type=${type}`); },
    getDatasourceHealth(connId) { return this.get(`/api/metrics/${connId}/health`); },
    getBatchDashboard(connIds) { return this.post('/api/metrics/batch/dashboard', { conn_ids: connIds }); },
    refreshMetrics(connId) { return this.post(`/api/metrics/${connId}/refresh`); },

    // Instance detail endpoints
    getInstanceAlertSummary() { return this.get('/api/instances/alert-summary'); },
    getInstanceSummary(datasourceId) { return this.get(`/api/instances/${datasourceId}/summary`); },
    getInstanceTraffic(datasourceId) { return this.get(`/api/instances/${datasourceId}/traffic`); },
    getInstanceVariables(datasourceId) { return this.get(`/api/instances/${datasourceId}/variables`); },
    getInstanceSessions(datasourceId) { return this.get(`/api/instances/${datasourceId}/sessions`); },
    terminateInstanceSession(datasourceId, sessionId) {
        return this.post(`/api/instances/${datasourceId}/sessions/${encodeURIComponent(sessionId)}/terminate`, {});
    },
    getInstanceTopSql(datasourceId, limit = 100) {
        return this.get(`/api/datasources/${datasourceId}/top-sql?limit=${limit}`);
    },
    explainSql(datasourceId, sqlText) {
        return this.post(`/api/datasources/${datasourceId}/explain-sql`, { sql_text: sqlText });
    },
    diagnoseSql(datasourceId, sqlText, sqlStats = {}) {
        return this.post(`/api/datasources/${datasourceId}/diagnose-sql`, { sql_text: sqlText, sql_stats: sqlStats });
    },

    // Chat endpoints
    getChatSessions(params = null) {
        const queryString = params ? `?${new URLSearchParams(params).toString()}` : '';
        return this.get(`/api/chat/sessions${queryString}`);
    },
    createChatSession(data) { return this.post('/api/chat/sessions', data); },
    deleteChatSession(id) { return this.delete(`/api/chat/sessions/${id}`); },
    clearSessionMessages(id) { return this.delete(`/api/chat/sessions/${id}/messages`); },
    getSessionMessages(sessionId) { return this.get(`/api/chat/sessions/${sessionId}/messages`); },
    getSessionInsights(sessionId) { return this.get(`/api/chat/sessions/${sessionId}/insights`); },
    getChatSkillAuthorizations() { return this.get('/api/chat/skill-authorizations'); },
    resolveChatApproval(sessionId, approvalId, data) { return this.post(`/api/chat/sessions/${sessionId}/approvals/${approvalId}/resolve`, data); },

    // Query endpoints
    executeQuery(data, options = {}) {
        return this.request('/api/query/execute', {
            method: 'POST',
            body: data,
            signal: options.signal
        });
    },
    cancelQuery(data, options = {}) {
        return this.request('/api/query/cancel', {
            method: 'POST',
            body: data,
            keepalive: Boolean(options.keepalive)
        });
    },
    explainQuery(data) { return this.post('/api/query/explain', data); },
    getQueryHistory() { return this.get('/api/query/history'); },
    getQueryContext(datasourceId, database = null) {
        let url = `/api/query/context?datasource_id=${datasourceId}`;
        if (database) url += `&database=${encodeURIComponent(database)}`;
        return this.get(url);
    },
    getSchemas(datasourceId, options = {}) {
        let url = `/api/query/schema/databases?datasource_id=${datasourceId}`;
        if (options.database) url += `&database=${encodeURIComponent(options.database)}`;
        return this.get(url);
    },
    getTables(datasourceId, options = {}) {
        let url = `/api/query/schema/tables?datasource_id=${datasourceId}`;
        if (options.schema) url += `&schema=${encodeURIComponent(options.schema)}`;
        if (options.database) url += `&database=${encodeURIComponent(options.database)}`;
        return this.get(url);
    },
    getColumns(datasourceId, table, options = {}) {
        let url = `/api/query/schema/columns?datasource_id=${datasourceId}&table=${encodeURIComponent(table)}`;
        if (options.schema) url += `&schema=${encodeURIComponent(options.schema)}`;
        if (options.database) url += `&database=${encodeURIComponent(options.database)}`;
        return this.get(url);
    },

    // Report endpoints
    getReports() { return this.get('/api/reports'); },
    generateReport(data) { return this.post('/api/reports/generate', data); },
    getReport(id) { return this.get(`/api/reports/${id}`); },
    getReportDownloadUrl(id, format) { return `/api/reports/${id}/download?format=${format}`; },
    async downloadReport(id, format) {
        const response = await fetch(`/api/reports/${id}/download?format=${format}`, {
            method: 'GET',
            credentials: 'same-origin'
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(err.detail || '下载失败');
        }

        // Get the blob and create download link
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `report_${id}.${format}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    },

    // AI Model endpoints
    getAIModels() { return this.get('/api/ai-models'); },
    createAIModel(data) { return this.post('/api/ai-models', data); },
    updateAIModel(id, data) { return this.put(`/api/ai-models/${id}`, data); },
    deleteAIModel(id) { return this.delete(`/api/ai-models/${id}`); },
    setDefaultAIModel(id) { return this.post(`/api/ai-models/${id}/set-default`); },
    testAIModelChat(id, data) { return this.post(`/api/ai-models/${id}/test-chat`, data); },

    getAlertTemplates() { return this.get('/api/inspections/templates'); },
    createAlertTemplate(data) { return this.post('/api/inspections/templates', data); },
    updateAlertTemplate(id, data) { return this.put(`/api/inspections/templates/${id}`, data); },
    toggleAlertTemplate(id, enabled) { return this.post(`/api/inspections/templates/${id}/toggle`, { enabled }); },

    // Document API
    getDocCategories(dbType = null) {
        const qs = dbType ? `?db_type=${dbType}` : '';
        return this.get(`/api/docs/categories${qs}`);
    },
    getCategoryDocuments(categoryId) {
        return this.get(`/api/docs/categories/${categoryId}/documents`);
    },
    getDocument(docId) {
        return this.get(`/api/docs/${docId}`);
    },
    createDocument(data) {
        return this.post('/api/docs', data);
    },
    updateDocument(docId, data) {
        return this.put(`/api/docs/${docId}`, data);
    },
    recompileDocument(docId) {
        return this.post(`/api/docs/${docId}/recompile`, {});
    },
    deleteDocument(docId) {
        return this.delete(`/api/docs/${docId}`);
    },
    exportDocument(docId) {
        const a = document.createElement('a');
        a.href = `/api/docs/${docId}/export`;
        a.setAttribute('download', '');
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    },
    async importDocument(categoryId, title, markdownContent) {
        return this.post('/api/docs', {
            category_id: categoryId,
            title: title,
            content: markdownContent,
        });
    },
    async getKnowledgeBases() {
        const categories = await this.getDocCategories();
        const items = [];

        const appendCategory = (category) => {
            items.push({
                id: category.id,
                name: category.name,
                db_type: category.db_type,
                is_active: true,
                document_count: category.document_count ?? 0,
            });
            for (const child of (category.children || [])) {
                appendCategory(child);
            }
        };

        for (const category of categories) {
            appendCategory(category);
        }

        return items;
    },

    // Skills
    getSkills() { return this.get('/api/skills'); },

    // Alerts
    getAlerts(params) {
        const queryString = params ? `?${new URLSearchParams(params).toString()}` : '';
        return this.get(`/api/alerts${queryString}`);
    },
    getAlert(id) { return this.get(`/api/alerts/${id}`); },
    getAlertContext(id) { return this.get(`/api/alerts/${id}/context`); },
    getAlertEventContext(id) { return this.get(`/api/alerts/events/${id}/context`); },
    acknowledgeAlert(id) { return this.post(`/api/alerts/${id}/acknowledge`, {}); },
    resolveAlert(id) { return this.post(`/api/alerts/${id}/resolve`, {}); },
    getSubscriptions() { return this.get('/api/alerts/subscriptions/list'); },
    createSubscription(data) { return this.post('/api/alerts/subscriptions', data); },
    updateSubscription(id, data) { return this.put(`/api/alerts/subscriptions/${id}`, data); },
    deleteSubscription(id) { return this.delete(`/api/alerts/subscriptions/${id}`); },
    testNotification(subscriptionId) { return this.post(`/api/alerts/subscriptions/${subscriptionId}/test`, {}); },
    getInspectionReportDetail(id) { return this.get(`/api/inspections/reports/detail/${id}`); },

    // Weixin Bot
    getWeixinBotBindings() { return this.get('/api/integration-bots'); },
    updateWeixinBotBinding(code, data) { return this.put(`/api/integration-bots/${code}`, data); },
    getWeixinBotStatus() { return this.get('/api/weixin/bot/binding/status'); },
    createWeixinLoginQrcode() { return this.post('/api/weixin/bot/login/qrcode', {}); },
    pollWeixinLoginStatus(qrcode) { return this.post('/api/weixin/bot/login/status', { qrcode }); }
};
