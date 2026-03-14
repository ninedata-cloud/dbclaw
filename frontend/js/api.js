/* API fetch wrapper */
const API = {
    async request(url, options = {}) {
        const defaultOpts = {
            headers: { 'Content-Type': 'application/json' },
        };
        const merged = { ...defaultOpts, ...options };

        // Inject auth token
        const token = localStorage.getItem('auth_token');
        if (token) {
            merged.headers['Authorization'] = `Bearer ${token}`;
        }

        if (merged.body && typeof merged.body === 'object') {
            merged.body = JSON.stringify(merged.body);
        }
        try {
            const response = await fetch(url, merged);
            if (!response.ok) {
                // Handle 401 - redirect to login
                if (response.status === 401) {
                    localStorage.removeItem('auth_token');
                    localStorage.removeItem('auth_user');
                    Store.set('currentUser', null);
                    window.location.hash = 'login';
                    throw new Error('会话已过期，请重新登录');
                }
                const err = await response.json().catch(() => ({ detail: response.statusText }));
                throw new Error(err.detail || err.message || '请求失败');
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

    async postFormData(url, formData) {
        const token = localStorage.getItem('auth_token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const response = await fetch(url, {
            method: 'POST',
            headers,
            body: formData
        });
        if (!response.ok) {
            if (response.status === 401) {
                localStorage.removeItem('auth_token');
                localStorage.removeItem('auth_user');
                Store.set('currentUser', null);
                window.location.hash = 'login';
                throw new Error('会话已过期，请重新登录');
            }
            const err = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(err.detail || err.message || '请求失败');
        }
        return await response.json();
    },

    // Auth endpoints
    login(username, password) { return this.post('/api/auth/login', { username, password }); },
    getMe() { return this.get('/api/auth/me'); },
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
    getDatasources() { return this.get('/api/datasources'); },
    createDatasource(data) { return this.post('/api/datasources', data); },
    updateDatasource(id, data) { return this.put(`/api/datasources/${id}`, data); },
    deleteDatasource(id) { return this.delete(`/api/datasources/${id}`); },
    testDatasource(id) { return this.post(`/api/datasources/${id}/test`); },

    // Host endpoints
    getHosts() { return this.get('/api/hosts'); },
    createHost(data) { return this.post('/api/hosts', data); },
    updateHost(id, data) { return this.put(`/api/hosts/${id}`, data); },
    deleteHost(id) { return this.delete(`/api/hosts/${id}`); },
    testHost(id) { return this.post(`/api/hosts/${id}/test`); },

    // Metrics endpoints
    getMetrics(connId, params = '') { return this.get(`/api/metrics/${connId}${params ? '?' + params : ''}`); },
    getLatestMetric(connId, type = 'db_status') { return this.get(`/api/metrics/${connId}/latest?metric_type=${type}`); },

    // Chat endpoints
    getChatSessions() { return this.get('/api/chat/sessions'); },
    createChatSession(data) { return this.post('/api/chat/sessions', data); },
    deleteChatSession(id) { return this.delete(`/api/chat/sessions/${id}`); },
    clearSessionMessages(id) { return this.delete(`/api/chat/sessions/${id}/messages`); },
    getSessionMessages(sessionId) { return this.get(`/api/chat/sessions/${sessionId}/messages`); },
    getHighRiskTools() { return this.get('/api/chat/high-risk-tools'); },

    // Query endpoints
    executeQuery(data) { return this.post('/api/query/execute', data); },
    explainQuery(data) { return this.post('/api/query/explain', data); },
    getQueryHistory() { return this.get('/api/query/history'); },
    getSchemas(datasourceId) { return this.get(`/api/query/schema/databases?datasource_id=${datasourceId}`); },
    getTables(datasourceId, schema = null) {
        let url = `/api/query/schema/tables?datasource_id=${datasourceId}`;
        if (schema) url += `&schema=${encodeURIComponent(schema)}`;
        return this.get(url);
    },
    getColumns(datasourceId, table, schema = null) {
        let url = `/api/query/schema/columns?datasource_id=${datasourceId}&table=${encodeURIComponent(table)}`;
        if (schema) url += `&schema=${encodeURIComponent(schema)}`;
        return this.get(url);
    },

    // Report endpoints
    getReports() { return this.get('/api/reports'); },
    generateReport(data) { return this.post('/api/reports/generate', data); },
    getReport(id) { return this.get(`/api/reports/${id}`); },
    getReportDownloadUrl(id, format) { return `/api/reports/${id}/download?format=${format}`; },
    async downloadReport(id, format) {
        const token = localStorage.getItem('auth_token');
        const headers = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const response = await fetch(`/api/reports/${id}/download?format=${format}`, {
            method: 'GET',
            headers
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

    // Knowledge Base endpoints
    getKnowledgeBases() { return this.get('/api/knowledge-bases'); },
    createKnowledgeBase(data) { return this.post('/api/knowledge-bases', data); },
    getKnowledgeBase(id) { return this.get(`/api/knowledge-bases/${id}`); },
    updateKnowledgeBase(id, data) { return this.put(`/api/knowledge-bases/${id}`, data); },
    deleteKnowledgeBase(id) { return this.delete(`/api/knowledge-bases/${id}`); },
    getDocuments(kbId) { return this.get(`/api/knowledge-bases/${kbId}/documents`); },
    async uploadDocument(kbId, file) {
        const formData = new FormData();
        formData.append('file', file);
        const token = localStorage.getItem('auth_token');
        const headers = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const response = await fetch(`/api/knowledge-bases/${kbId}/documents`, {
            method: 'POST',
            headers,
            body: formData,
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(err.detail || '上传失败');
        }
        return await response.json();
    },
    deleteDocument(kbId, docId) { return this.delete(`/api/knowledge-bases/${kbId}/documents/${docId}`); },
    async getDocumentContent(kbId, docId) {
        const token = localStorage.getItem('auth_token');
        const headers = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const response = await fetch(`/api/knowledge-bases/${kbId}/documents/${docId}/content`, { headers });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(err.detail || '获取文档内容失败');
        }
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/pdf')) {
            return { type: 'pdf', url: `/api/knowledge-bases/${kbId}/documents/${docId}/content` };
        }
        return await response.json();
    },

    // Skills
    getSkills() { return this.get('/api/skills'); }

};
