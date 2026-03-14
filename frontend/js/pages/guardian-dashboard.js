/* Guardian Dashboard page */
const GuardianDashboardPage = {
    refreshInterval: null,

    async render() {
        const container = DOM.$('#page-content');
        Header.render('AI Guardian System');
        container.innerHTML = `
            <div class="guardian-dashboard">
                <div class="dashboard-header">
                    <h1>AI Guardian System</h1>
                    <p class="subtitle">智能数据库守护系统</p>
                </div>

                <div class="health-overview" id="health-overview">
                    <div class="loading">Loading...</div>
                </div>

                <div class="database-grid" id="database-grid">
                    <div class="loading">Loading...</div>
                </div>

                <div class="anomaly-stream" id="anomaly-stream">
                    <h2>Recent Anomalies</h2>
                    <div class="loading">Loading...</div>
                </div>
            </div>
        `;

        await this.loadDashboardData();
        this.startAutoRefresh();

        // Return cleanup function for Router
        return () => this.destroy();
    },

    async loadDashboardData() {
        try {
            // Load overview
            const overview = await API.get('/api/guardian/dashboard/overview');
            this.renderOverview(overview);

            // Load datasources with importance
            const datasources = await API.getDatasources();
            await this.renderDatabaseGrid(datasources);

            // Load recent anomalies
            await this.loadRecentAnomalies(datasources);

        } catch (error) {
            console.error('Failed to load dashboard data:', error);
            const container = DOM.$('#page-content');
            container.innerHTML = `
                <div class="empty-state">
                    <h3>Failed to load Guardian Dashboard</h3>
                    <p>${error.message}</p>
                </div>
            `;
        }
    },

    renderOverview(data) {
        const container = DOM.$('#health-overview');
        if (!container) return; // Guard against navigation away

        const totalDatasources = data.datasources.total;
        const criticalCount = data.anomalies.by_severity.CRITICAL || 0;
        const warningCount = data.anomalies.by_severity.WARNING || 0;

        // Calculate health score (simple formula)
        const healthScore = Math.max(0, 100 - (criticalCount * 10 + warningCount * 5));

        container.innerHTML = `
            <div class="health-score-card">
                <div class="health-score ${this.getHealthClass(healthScore)}">
                    ${healthScore}
                </div>
                <div class="health-label">Overall Health</div>
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">${totalDatasources}</div>
                    <div class="stat-label">Total Databases</div>
                </div>

                <div class="stat-card critical">
                    <div class="stat-value">${data.datasources.by_level.core || 0}</div>
                    <div class="stat-label">核心系统</div>
                </div>

                <div class="stat-card important">
                    <div class="stat-value">${data.datasources.by_level.production || 0}</div>
                    <div class="stat-label">生产系统</div>
                </div>

                <div class="stat-card normal">
                    <div class="stat-value">${data.datasources.by_level.development || 0}</div>
                    <div class="stat-label">开发测试</div>
                </div>

                <div class="stat-card normal">
                    <div class="stat-value">${data.datasources.by_level.temporary || 0}</div>
                    <div class="stat-label">临时</div>
                </div>
            </div>

            <div class="anomaly-summary">
                <div class="anomaly-stat critical">
                    <span class="icon">🔴</span>
                    <span class="count">${criticalCount}</span>
                    <span class="label">Critical Issues</span>
                </div>
                <div class="anomaly-stat warning">
                    <span class="icon">🟡</span>
                    <span class="count">${warningCount}</span>
                    <span class="label">Warnings</span>
                </div>
            </div>
        `;
    },

    async renderDatabaseGrid(datasources) {
        const container = DOM.$('#database-grid');
        if (!container) return; // Guard against navigation away

        if (!datasources || datasources.length === 0) {
            container.innerHTML = '<p class="empty-state">No datasources configured</p>';
            return;
        }

        // Group by importance level
        const grouped = {
            core: [],
            production: [],
            development: [],
            temporary: []
        };

        for (const ds of datasources) {
            const level = ds.importance_level || 'production';
            if (grouped[level]) {
                grouped[level].push(ds);
            }
        }

        container.innerHTML = `
            ${this.renderLevelSection('core', '核心系统', grouped.core)}
            ${this.renderLevelSection('production', '生产系统', grouped.production)}
            ${this.renderLevelSection('development', '开发测试', grouped.development)}
            ${this.renderLevelSection('temporary', '临时', grouped.temporary)}
        `;
    },

    renderLevelSection(level, label, datasources) {
        if (datasources.length === 0) return '';

        const levelColors = {
            core: '#ef4444',
            production: '#f59e0b',
            development: '#3b82f6',
            temporary: '#6b7280'
        };

        const cards = datasources.map(ds => this.renderDatabaseCard(ds, level)).join('');

        return `
            <div class="tier-section ${level}">
                <h3 class="tier-header">
                    <span class="tier-badge" style="background-color: ${levelColors[level]}">${label}</span>
                    <span class="tier-count">${datasources.length}</span>
                </h3>
                <div class="database-cards">
                    ${cards}
                </div>
            </div>
        `;
    },

    renderDatabaseCard(datasource, level) {
        const interval = datasource.monitoring_interval || 60;
        const levelLabels = {
            core: '核心系统',
            production: '生产系统',
            development: '开发测试',
            temporary: '临时'
        };

        return `
            <div class="database-card ${level}" data-id="${datasource.id}">
                <div class="card-header">
                    <h4>${datasource.name}</h4>
                    <span class="db-type">${datasource.db_type}</span>
                </div>
                <div class="card-body">
                    <div class="importance-info">
                        <span class="info-label">重要等级:</span>
                        <span class="info-value">${levelLabels[level]}</span>
                    </div>
                    <div class="importance-info">
                        <span class="info-label">监控间隔:</span>
                        <span class="info-value">${interval}s</span>
                    </div>
                    <div class="importance-info">
                        <span class="info-label">检测模式:</span>
                        <span class="info-value">${level === 'core' ? 'realtime' : 'neartime'}</span>
                    </div>
                </div>
                <div class="card-actions">
                    <button onclick="GuardianDashboardPage.viewDetails(${datasource.id})" class="btn-small">
                        View Details
                    </button>
                    <button onclick="GuardianDashboardPage.viewAnomalies(${datasource.id})" class="btn-small">
                        Anomalies
                    </button>
                </div>
            </div>
        `;
    },

    async loadRecentAnomalies(datasources) {
        const container = DOM.$('#anomaly-stream');
        if (!container) return; // Guard against navigation away

        try {
            // Collect anomalies from all datasources
            const allAnomalies = [];

            for (const ds of datasources) {
                try {
                    const data = await API.get(`/api/guardian/anomalies/${ds.id}?limit=10`);
                    // Add datasource info to each anomaly
                    data.anomalies.forEach(a => {
                        a.datasource_name = ds.name;
                        a.datasource_id = ds.id;
                        allAnomalies.push(a);
                    });
                } catch (error) {
                    console.warn(`Failed to load anomalies for datasource ${ds.id}:`, error);
                }
            }

            // Sort by detected_at descending
            allAnomalies.sort((a, b) => new Date(b.detected_at) - new Date(a.detected_at));

            // Take top 20
            const recentAnomalies = allAnomalies.slice(0, 20);

            container.innerHTML = `
                <h2>Recent Anomalies</h2>
                ${recentAnomalies.length === 0 ?
                    '<p class="empty-state">No recent anomalies detected</p>' :
                    this.renderRecentAnomalyStream(recentAnomalies)
                }
            `;
        } catch (error) {
            console.error('Failed to load recent anomalies:', error);
            container.innerHTML = `
                <h2>Recent Anomalies</h2>
                <p class="error-state">Failed to load anomalies: ${error.message}</p>
            `;
        }
    },

    renderRecentAnomalyStream(anomalies) {
        return `
            <div class="anomaly-stream-list">
                ${anomalies.map(a => `
                    <div class="anomaly-stream-item ${a.severity.toLowerCase()}">
                        <div class="anomaly-time">${this.formatRelativeTime(a.detected_at)}</div>
                        <div class="anomaly-content">
                            <div class="anomaly-source">
                                <span class="datasource-name">${a.datasource_name}</span>
                                <span class="severity-badge ${a.severity.toLowerCase()}">${a.severity}</span>
                            </div>
                            <div class="anomaly-message">
                                ${a.anomaly_type}: ${a.current_value?.toFixed(2)} (baseline: ${a.baseline_value?.toFixed(2)}, deviation: ${a.deviation_percent?.toFixed(1)}%)
                            </div>
                            <div class="anomaly-status">
                                <span class="status-badge ${a.status}">${a.status}</span>
                                ${a.was_auto_fixed ? '<span class="auto-fixed-tag">Auto-fixed</span>' : ''}
                                ${a.diagnosis_decision ? `<span class="diagnosis-decision ${a.diagnosis_decision}">${a.diagnosis_decision === 'diagnosed' ? '✓ Diagnosed' : '⏭ Skipped'}</span>` : ''}
                            </div>
                            ${a.diagnosis_decision_reason ? `
                                <div class="diagnosis-reason">
                                    <span class="reason-label">Decision:</span>
                                    <span class="reason-text">${a.diagnosis_decision_reason}</span>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    },

    formatRelativeTime(timestamp) {
        const now = new Date();
        const time = new Date(timestamp);
        const diffMs = now - time;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        return time.toLocaleDateString();
    },

    getHealthClass(score) {
        if (score >= 90) return 'excellent';
        if (score >= 70) return 'good';
        if (score >= 50) return 'fair';
        return 'poor';
    },

    async viewDetails(datasourceId) {
        // Navigate to datasource details with guardian info
        Router.navigate(`datasources/${datasourceId}`);
    },

    async viewAnomalies(datasourceId) {
        try {
            const anomalies = await API.get(`/api/guardian/anomalies/${datasourceId}`);
            this.showAnomalyModal(datasourceId, anomalies);
        } catch (error) {
            console.error('Failed to load anomalies:', error);
            alert('Failed to load anomalies: ' + error.message);
        }
    },

    showAnomalyModal(datasourceId, data) {
        const modal = DOM.el('div', { className: 'modal' });
        modal.innerHTML = `
            <div class="modal-content large">
                <div class="modal-header">
                    <h2>Anomalies - Datasource ${datasourceId}</h2>
                    <button class="close-btn" onclick="this.closest('.modal').remove()">×</button>
                </div>
                <div class="modal-body">
                    ${data.anomalies.length === 0 ?
                        '<p class="empty-state">No anomalies detected</p>' :
                        this.renderAnomalyList(data.anomalies)
                    }
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    },

    renderAnomalyList(anomalies) {
        return `
            <div class="anomaly-list">
                ${anomalies.map(a => `
                    <div class="anomaly-item ${a.severity.toLowerCase()}" onclick="GuardianDashboardPage.showAnomalyDetail(${a.id})">
                        <div class="anomaly-header">
                            <span class="severity-badge ${a.severity.toLowerCase()}">${a.severity}</span>
                            <span class="timestamp">${new Date(a.detected_at).toLocaleString()}</span>
                        </div>
                        <div class="anomaly-details">
                            <div class="detail-row">
                                <span class="label">Type:</span>
                                <span class="value">${a.anomaly_type}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">Deviation:</span>
                                <span class="value">${a.deviation_percent?.toFixed(2)}%</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">Baseline:</span>
                                <span class="value">${a.baseline_value?.toFixed(2)}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">Current:</span>
                                <span class="value">${a.current_value?.toFixed(2)}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">Status:</span>
                                <span class="value status-${a.status}">${a.status}</span>
                            </div>
                            ${a.ai_diagnosis ? '<div class="ai-diagnosis-badge">✓ AI Diagnosed</div>' : ''}
                            ${a.was_auto_fixed ? '<div class="auto-fixed-badge">Auto-fixed</div>' : ''}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    },

    async showAnomalyDetail(anomalyId) {
        try {
            // Find the anomaly in current data
            const allAnomalies = [];
            const datasources = await API.getDatasources();

            for (const ds of datasources) {
                try {
                    const data = await API.get(`/api/guardian/anomalies/${ds.id}`);
                    allAnomalies.push(...data.anomalies.map(a => ({...a, datasource_id: ds.id, datasource_name: ds.name})));
                } catch (error) {
                    console.warn(`Failed to load anomalies for datasource ${ds.id}:`, error);
                }
            }

            const anomaly = allAnomalies.find(a => a.id === anomalyId);
            if (!anomaly) {
                alert('Anomaly not found');
                return;
            }

            // Fetch full details
            const detail = await API.get(`/api/guardian/anomalies/${anomaly.datasource_id}/${anomalyId}`);
            this.showAnomalyDetailModal(detail, anomaly.datasource_name);

        } catch (error) {
            console.error('Failed to load anomaly detail:', error);
            alert('Failed to load anomaly detail: ' + error.message);
        }
    },

    showAnomalyDetailModal(anomaly, datasourceName) {
        const modal = DOM.el('div', { className: 'modal' });

        // Parse JSON fields
        let affectedMetrics = [];
        let recommendedActions = [];
        let contextSnapshot = {};

        try {
            affectedMetrics = typeof anomaly.affected_metrics === 'string'
                ? JSON.parse(anomaly.affected_metrics)
                : anomaly.affected_metrics || [];
        } catch (e) {
            console.error('Failed to parse affected_metrics:', e);
        }

        try {
            recommendedActions = typeof anomaly.recommended_actions === 'string'
                ? JSON.parse(anomaly.recommended_actions)
                : anomaly.recommended_actions || [];
        } catch (e) {
            console.error('Failed to parse recommended_actions:', e);
        }

        try {
            contextSnapshot = typeof anomaly.context_snapshot === 'string'
                ? JSON.parse(anomaly.context_snapshot)
                : anomaly.context_snapshot || {};
        } catch (e) {
            console.error('Failed to parse context_snapshot:', e);
        }

        modal.innerHTML = `
            <div class="modal-content large">
                <div class="modal-header">
                    <h2>Anomaly Detail #${anomaly.id}</h2>
                    <button class="close-btn" onclick="this.closest('.modal').remove()">×</button>
                </div>
                <div class="modal-body anomaly-detail-modal">
                    <div class="detail-section">
                        <h3>Basic Information</h3>
                        <div class="info-grid">
                            <div class="info-item">
                                <span class="info-label">Database:</span>
                                <span class="info-value">${datasourceName}</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Detected At:</span>
                                <span class="info-value">${new Date(anomaly.detected_at).toLocaleString()}</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Severity:</span>
                                <span class="severity-badge ${anomaly.severity.toLowerCase()}">${anomaly.severity}</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Status:</span>
                                <span class="status-badge ${anomaly.status}">${anomaly.status}</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Affected Metrics:</span>
                                <span class="info-value">${affectedMetrics.join(', ')}</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Confidence:</span>
                                <span class="info-value">${(anomaly.confidence * 100).toFixed(0)}%</span>
                            </div>
                        </div>
                    </div>

                    <div class="detail-section">
                        <h3>Metric Analysis</h3>
                        <div class="metric-comparison">
                            <div class="metric-box">
                                <div class="metric-label">Baseline Value</div>
                                <div class="metric-value">${anomaly.baseline_value?.toFixed(2)}</div>
                            </div>
                            <div class="metric-arrow">→</div>
                            <div class="metric-box current">
                                <div class="metric-label">Current Value</div>
                                <div class="metric-value">${anomaly.current_value?.toFixed(2)}</div>
                            </div>
                            <div class="metric-box deviation">
                                <div class="metric-label">Deviation</div>
                                <div class="metric-value">${anomaly.deviation_percent?.toFixed(2)}%</div>
                            </div>
                        </div>
                    </div>

                    ${anomaly.ai_diagnosis ? `
                        <div class="detail-section">
                            <h3>🤖 AI Diagnosis</h3>
                            <div class="diagnosis-content markdown-content">
                                ${this.renderMarkdown(anomaly.ai_diagnosis)}
                            </div>
                        </div>
                    ` : `
                        <div class="detail-section">
                            <h3>🤖 AI Diagnosis</h3>
                            <p class="empty-state">AI diagnosis pending...</p>
                            <button class="btn btn-primary" onclick="GuardianDashboardPage.triggerDiagnosis(${anomaly.datasource_id}, ${anomaly.id})">
                                Trigger AI Diagnosis
                            </button>
                        </div>
                    `}

                    ${anomaly.root_cause ? `
                        <div class="detail-section">
                            <h3>🔍 Root Cause</h3>
                            <div class="root-cause-content markdown-content">
                                ${this.renderMarkdown(anomaly.root_cause)}
                            </div>
                        </div>
                    ` : ''}

                    ${recommendedActions && recommendedActions.length > 0 ? `
                        <div class="detail-section">
                            <h3>💡 Recommended Actions</h3>
                            <div class="actions-list">
                                ${recommendedActions.map((action, idx) => `
                                    <div class="action-item">
                                        <span class="action-number">${idx + 1}</span>
                                        <span class="action-text">${action}</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}

                    <div class="detail-section">
                        <h3>📊 System Context</h3>
                        <div class="context-grid">
                            ${Object.entries(contextSnapshot).slice(0, 12).map(([key, value]) => `
                                <div class="context-item">
                                    <span class="context-label">${key}:</span>
                                    <span class="context-value">${typeof value === 'number' ? value.toFixed(2) : value}</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    },

    renderMarkdown(text) {
        if (!text) return '';

        console.log('[renderMarkdown] Input text length:', text.length);
        console.log('[renderMarkdown] typeof marked:', typeof marked);
        console.log('[renderMarkdown] typeof window.marked:', typeof window.marked);

        // Check if marked is available
        if (typeof marked === 'undefined' && typeof window.marked === 'undefined') {
            console.error('[renderMarkdown] marked library not loaded, using fallback');
            return this.escapeHtml(text).replace(/\n/g, '<br>');
        }

        // Use window.marked if marked is not directly available
        const markedLib = typeof marked !== 'undefined' ? marked : window.marked;
        console.log('[renderMarkdown] Using marked library:', markedLib);

        try {
            // For marked v11+, use the new API
            if (markedLib && markedLib.parse) {
                console.log('[renderMarkdown] Using marked.parse()');
                const result = markedLib.parse(text, {
                    breaks: true,
                    gfm: true
                });
                console.log('[renderMarkdown] Parse successful, result length:', result.length);
                return result;
            }

            // Fallback for older versions
            if (markedLib && typeof markedLib === 'function') {
                console.log('[renderMarkdown] Using marked() function');
                return markedLib(text);
            }

            console.error('[renderMarkdown] marked.parse not available');
            return this.escapeHtml(text).replace(/\n/g, '<br>');
        } catch (error) {
            console.error('[renderMarkdown] Markdown rendering error:', error);
            return this.escapeHtml(text).replace(/\n/g, '<br>');
        }
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    async triggerDiagnosis(datasourceId, anomalyId) {
        try {
            const button = event.target;
            button.disabled = true;
            button.textContent = 'Diagnosing...';

            const result = await API.post(`/api/guardian/anomalies/${datasourceId}/${anomalyId}/diagnose`);

            if (result.success) {
                alert('AI diagnosis completed successfully!');
                // Close modal and refresh
                document.querySelector('.modal').remove();
                await this.showAnomalyDetail(anomalyId);
            } else {
                alert('Diagnosis failed: ' + (result.error || 'Unknown error'));
                button.disabled = false;
                button.textContent = 'Trigger AI Diagnosis';
            }
        } catch (error) {
            console.error('Failed to trigger diagnosis:', error);
            alert('Failed to trigger diagnosis: ' + error.message);
            event.target.disabled = false;
            event.target.textContent = 'Trigger AI Diagnosis';
        }
    },

    startAutoRefresh() {
        // Refresh every 30 seconds
        this.refreshInterval = setInterval(() => {
            this.loadDashboardData();
        }, 30000);
    },

    destroy() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
};
