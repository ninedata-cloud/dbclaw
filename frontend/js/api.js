/* API fetch wrapper */
const API = {
    async request(url, options = {}) {
        const defaultOpts = {
            headers: { 'Content-Type': 'application/json' },
        };
        const merged = { ...defaultOpts, ...options };
        if (merged.body && typeof merged.body === 'object') {
            merged.body = JSON.stringify(merged.body);
        }
        try {
            const response = await fetch(url, merged);
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: response.statusText }));
                throw new Error(err.detail || err.message || 'Request failed');
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

    // Connection endpoints
    getConnections() { return this.get('/api/connections'); },
    createConnection(data) { return this.post('/api/connections', data); },
    updateConnection(id, data) { return this.put(`/api/connections/${id}`, data); },
    deleteConnection(id) { return this.delete(`/api/connections/${id}`); },
    testConnection(id) { return this.post(`/api/connections/${id}/test`); },

    // SSH Host endpoints
    getSSHHosts() { return this.get('/api/ssh-hosts'); },
    createSSHHost(data) { return this.post('/api/ssh-hosts', data); },
    updateSSHHost(id, data) { return this.put(`/api/ssh-hosts/${id}`, data); },
    deleteSSHHost(id) { return this.delete(`/api/ssh-hosts/${id}`); },
    testSSHHost(id) { return this.post(`/api/ssh-hosts/${id}/test`); },

    // Metrics endpoints
    getMetrics(connId, params = '') { return this.get(`/api/metrics/${connId}${params ? '?' + params : ''}`); },
    getLatestMetric(connId, type = 'db_status') { return this.get(`/api/metrics/${connId}/latest?metric_type=${type}`); },

    // Chat endpoints
    getChatSessions() { return this.get('/api/chat/sessions'); },
    createChatSession(data) { return this.post('/api/chat/sessions', data); },
    deleteChatSession(id) { return this.delete(`/api/chat/sessions/${id}`); },
    clearSessionMessages(id) { return this.delete(`/api/chat/sessions/${id}/messages`); },
    getSessionMessages(sessionId) { return this.get(`/api/chat/sessions/${sessionId}/messages`); },

    // Query endpoints
    executeQuery(data) { return this.post('/api/query/execute', data); },
    explainQuery(data) { return this.post('/api/query/explain', data); },
    getQueryHistory() { return this.get('/api/query/history'); },

    // Report endpoints
    getReports() { return this.get('/api/reports'); },
    generateReport(data) { return this.post('/api/reports/generate', data); },
    getReport(id) { return this.get(`/api/reports/${id}`); },
    getReportDownloadUrl(id, format) { return `/api/reports/${id}/download?format=${format}`; },

    // AI Model endpoints
    getAIModels() { return this.get('/api/ai-models'); },
    createAIModel(data) { return this.post('/api/ai-models', data); },
    updateAIModel(id, data) { return this.put(`/api/ai-models/${id}`, data); },
    deleteAIModel(id) { return this.delete(`/api/ai-models/${id}`); },
    setDefaultAIModel(id) { return this.post(`/api/ai-models/${id}/set-default`); },
};
