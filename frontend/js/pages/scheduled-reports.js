/**
 * Scheduled Reports Page
 *
 * Manages automated report generation schedules for datasources.
 */

let currentConfigs = [];
let currentHistory = [];
let countdownIntervals = {};

const ScheduledReportsPage = {
    async render() {
        const content = document.getElementById('page-content');
        content.innerHTML = `
            <div class="scheduled-reports-page">
                <div class="page-header-section">
                    <h1>Scheduled Reports</h1>
                    <div class="page-actions">
                        <button id="refresh-configs-btn" class="btn btn-secondary">
                            <i data-lucide="refresh-cw"></i> Refresh
                        </button>
                        <button id="new-schedule-btn" class="btn btn-primary">
                            <i data-lucide="plus"></i> New Schedule
                        </button>
                    </div>
                </div>

                <div id="scheduled-reports-stats" class="stats-section"></div>

                <div class="scheduled-configs-section">
                    <h2>Active Schedules</h2>
                    <div id="scheduled-configs-container" class="configs-grid"></div>
                </div>
            </div>
        `;

        // Initialize icons
        if (window.lucide) {
            lucide.createIcons();
        }

        await initScheduledReportsPage();
    }
};

async function initScheduledReportsPage() {
    console.log('Initializing scheduled reports page');

    // Load initial data
    await loadConfigs();
    await loadStats();

    // Setup event listeners
    setupEventListeners();

    // Start countdown timers
    startCountdownTimers();
}

function setupEventListeners() {
    // New schedule button
    const newScheduleBtn = document.getElementById('new-schedule-btn');
    if (newScheduleBtn) {
        newScheduleBtn.addEventListener('click', showNewScheduleModal);
    }

    // Refresh button
    const refreshBtn = document.getElementById('refresh-configs-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            loadConfigs();
            loadStats();
        });
    }
}

async function loadConfigs() {
    try {
        const configs = await API.getScheduledReportConfigs();
        currentConfigs = configs;
        renderConfigs(configs);
    } catch (error) {
        console.error('Error loading configs:', error);
        Toast.error('Failed to load scheduled report configurations');
    }
}

async function loadStats() {
    try {
        const stats = await API.getScheduledReportStats();
        renderStats(stats);
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

function renderStats(stats) {
    const statsContainer = document.getElementById('scheduled-reports-stats');
    if (!statsContainer) return;

    statsContainer.innerHTML = `
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Configs</div>
                <div class="stat-value">${stats.total_configs}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Enabled</div>
                <div class="stat-value">${stats.enabled_configs}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Reports Today</div>
                <div class="stat-value">${stats.reports_today}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Success Rate</div>
                <div class="stat-value">${stats.success_rate}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Avg Duration</div>
                <div class="stat-value">${stats.average_duration_seconds ? stats.average_duration_seconds.toFixed(1) + 's' : 'N/A'}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Failed</div>
                <div class="stat-value error">${stats.failed_count}</div>
            </div>
        </div>
    `;
}

function renderConfigs(configs) {
    const container = document.getElementById('scheduled-configs-container');
    if (!container) return;

    if (configs.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>No scheduled report configurations found.</p>
                <button class="btn btn-primary" onclick="window.scheduledReports.showNewScheduleModal()">
                    Create First Schedule
                </button>
            </div>
        `;
        return;
    }

    container.innerHTML = configs.map(config => `
        <div class="schedule-card ${config.enabled ? 'enabled' : 'disabled'}" data-config-id="${config.id}">
            <div class="schedule-card-header">
                <div class="schedule-title">
                    <h3>${config.datasource_name}</h3>
                    <span class="badge badge-${config.importance_level}">${config.importance_level}</span>
                    <span class="badge badge-${config.datasource_type}">${config.datasource_type}</span>
                </div>
                <div class="schedule-status">
                    <span class="status-indicator ${config.enabled ? 'active' : 'inactive'}"></span>
                    <span>${config.enabled ? 'Enabled' : 'Disabled'}</span>
                </div>
            </div>

            <div class="schedule-card-body">
                <div class="schedule-info">
                    <div class="info-item">
                        <span class="info-label">Interval:</span>
                        <span class="info-value">${config.schedule_interval_display}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">Report Type:</span>
                        <span class="info-value">${config.report_type}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">AI Analysis:</span>
                        <span class="info-value">${config.use_ai_analysis ? 'Yes' : 'No'}</span>
                    </div>
                    ${config.last_generated_at ? `
                        <div class="info-item">
                            <span class="info-label">Last Generated:</span>
                            <span class="info-value">${formatDateTime(config.last_generated_at)}</span>
                        </div>
                    ` : ''}
                    ${config.next_scheduled_at && config.enabled ? `
                        <div class="info-item">
                            <span class="info-label">Next Run:</span>
                            <span class="info-value countdown" data-target="${config.next_scheduled_at}" data-config-id="${config.id}">
                                ${formatDateTime(config.next_scheduled_at)}
                            </span>
                        </div>
                    ` : ''}
                </div>
            </div>

            <div class="schedule-card-actions">
                <button class="btn btn-sm btn-secondary" onclick="window.scheduledReports.showConfigModal(${config.id})">
                    Configure
                </button>
                <button class="btn btn-sm btn-secondary" onclick="window.scheduledReports.showHistoryModal(${config.datasource_id})">
                    View History
                </button>
                <button class="btn btn-sm btn-primary" onclick="window.scheduledReports.triggerNow(${config.datasource_id})" ${!config.enabled ? 'disabled' : ''}>
                    Trigger Now
                </button>
                <button class="btn btn-sm ${config.enabled ? 'btn-warning' : 'btn-success'}"
                        onclick="window.scheduledReports.toggleEnabled(${config.id}, ${!config.enabled})">
                    ${config.enabled ? 'Disable' : 'Enable'}
                </button>
            </div>
        </div>
    `).join('');
}

function startCountdownTimers() {
    // Clear existing intervals
    Object.values(countdownIntervals).forEach(interval => clearInterval(interval));
    countdownIntervals = {};

    // Start new intervals
    document.querySelectorAll('.countdown').forEach(element => {
        const configId = element.dataset.configId;
        const targetTime = new Date(element.dataset.target);

        const interval = setInterval(() => {
            const now = new Date();
            const diff = targetTime - now;

            if (diff <= 0) {
                element.textContent = 'Generating...';
                clearInterval(interval);
                setTimeout(() => loadConfigs(), 5000);
            } else {
                element.textContent = formatCountdown(diff);
            }
        }, 1000);

        countdownIntervals[configId] = interval;
    });
}

function formatCountdown(ms) {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) {
        return `in ${days}d ${hours % 24}h`;
    } else if (hours > 0) {
        return `in ${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
        return `in ${minutes}m ${seconds % 60}s`;
    } else {
        return `in ${seconds}s`;
    }
}

function formatDateTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString();
}

async function showNewScheduleModal() {
    try {
        const allDatasources = await API.getDatasources();
        const configuredIds = new Set(currentConfigs.map(c => c.datasource_id));
        const availableDatasources = allDatasources.filter(ds =>
            !configuredIds.has(ds.id) && ds.importance_level !== 'temporary'
        );

        if (availableDatasources.length === 0) {
            Toast.info('All eligible datasources already have scheduled reports');
            return;
        }

        const aiModels = await API.getAIModels();

        const modalContent = `
            <h2>Create Scheduled Report</h2>
            <form id="new-schedule-form">
                <div class="form-group">
                    <label for="schedule-datasource">Datasource *</label>
                    <select id="schedule-datasource" required>
                        <option value="">Select datasource...</option>
                        ${availableDatasources.map(ds => `
                            <option value="${ds.id}" data-importance="${ds.importance_level}">
                                ${ds.name} (${ds.db_type} - ${ds.importance_level})
                            </option>
                        `).join('')}
                    </select>
                </div>

                <div class="form-group">
                    <label>Schedule Interval</label>
                    <input type="text" id="schedule-interval-display" readonly class="readonly-input"
                           value="Select a datasource to see interval">
                    <small class="form-help">Interval is automatically determined by datasource importance level</small>
                </div>

                <div class="form-group">
                    <label for="schedule-report-type">Report Type</label>
                    <select id="schedule-report-type">
                        <option value="comprehensive">Comprehensive</option>
                        <option value="performance">Performance</option>
                        <option value="security">Security</option>
                    </select>
                </div>

                <div class="form-group">
                    <label>
                        <input type="checkbox" id="schedule-use-ai">
                        Use AI Analysis
                    </label>
                </div>

                <div id="ai-options" style="display: none;">
                    <div class="form-group">
                        <label for="schedule-ai-model">AI Model</label>
                        <select id="schedule-ai-model">
                            <option value="">Select model...</option>
                            ${aiModels.map(model => `
                                <option value="${model.id}">${model.name}</option>
                            `).join('')}
                        </select>
                    </div>
                </div>

                <div class="form-group">
                    <label for="schedule-retention">Retention Days</label>
                    <input type="number" id="schedule-retention" value="30" min="1" max="365">
                    <small class="form-help">Days to keep scheduled reports before automatic cleanup</small>
                </div>

                <div class="form-actions" style="margin-top: 20px; text-align: right;">
                    <button type="button" class="btn btn-secondary" onclick="Modal.hide()">Cancel</button>
                    <button type="submit" class="btn btn-primary">Create Schedule</button>
                </div>
            </form>
        `;

        Modal.show({
            title: 'Create Scheduled Report',
            content: modalContent,
            size: 'large'
        });

        const datasourceSelect = document.getElementById('schedule-datasource');
        const intervalDisplay = document.getElementById('schedule-interval-display');
        const useAiCheckbox = document.getElementById('schedule-use-ai');
        const aiOptions = document.getElementById('ai-options');

        datasourceSelect.addEventListener('change', (e) => {
            const option = e.target.selectedOptions[0];
            const importance = option.dataset.importance;
            const intervalMap = {
                'core': '1 hour',
                'production': '4 hours',
                'development': '24 hours',
                'test': '24 hours'
            };
            intervalDisplay.value = intervalMap[importance] || 'Unknown';
        });

        useAiCheckbox.addEventListener('change', (e) => {
            aiOptions.style.display = e.target.checked ? 'block' : 'none';
        });

        document.getElementById('new-schedule-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            await createSchedule();
        });

    } catch (error) {
        console.error('Error showing new schedule modal:', error);
        Toast.error('Failed to load form data');
    }
}

async function createSchedule() {
    try {
        const datasourceId = parseInt(document.getElementById('schedule-datasource').value);
        const reportType = document.getElementById('schedule-report-type').value;
        const useAi = document.getElementById('schedule-use-ai').checked;
        const aiModelId = useAi ? parseInt(document.getElementById('schedule-ai-model').value) : null;
        const retentionDays = parseInt(document.getElementById('schedule-retention').value);

        if (!datasourceId) {
            Toast.error('Please select a datasource');
            return;
        }

        if (useAi && !aiModelId) {
            Toast.error('Please select an AI model');
            return;
        }

        const data = {
            datasource_id: datasourceId,
            enabled: true,
            report_type: reportType,
            use_ai_analysis: useAi,
            ai_model_id: aiModelId,
            kb_ids: [],
            retention_days: retentionDays
        };

        await API.createScheduledReportConfig(data);
        Toast.success('Scheduled report created successfully');
        Modal.hide();
        await loadConfigs();

    } catch (error) {
        console.error('Error creating schedule:', error);
        Toast.error(error.message || 'Failed to create schedule');
    }
}

async function showConfigModal(configId) {
    const config = currentConfigs.find(c => c.id === configId);
    if (!config) return;

    try {
        const aiModels = await API.getAIModels();

        const modalContent = `
            <h2>Configure Schedule</h2>
            <form id="edit-schedule-form">
                <div class="form-group">
                    <label>Datasource</label>
                    <input type="text" value="${config.datasource_name}" readonly class="readonly-input">
                </div>

                <div class="form-group">
                    <label>Schedule Interval</label>
                    <input type="text" value="${config.schedule_interval_display}" readonly class="readonly-input">
                </div>

                <div class="form-group">
                    <label for="edit-report-type">Report Type</label>
                    <select id="edit-report-type">
                        <option value="comprehensive" ${config.report_type === 'comprehensive' ? 'selected' : ''}>Comprehensive</option>
                        <option value="performance" ${config.report_type === 'performance' ? 'selected' : ''}>Performance</option>
                        <option value="security" ${config.report_type === 'security' ? 'selected' : ''}>Security</option>
                    </select>
                </div>

                <div class="form-group">
                    <label>
                        <input type="checkbox" id="edit-use-ai" ${config.use_ai_analysis ? 'checked' : ''}>
                        Use AI Analysis
                    </label>
                </div>

                <div id="edit-ai-options" style="display: ${config.use_ai_analysis ? 'block' : 'none'};">
                    <div class="form-group">
                        <label for="edit-ai-model">AI Model</label>
                        <select id="edit-ai-model">
                            <option value="">Select model...</option>
                            ${aiModels.map(model => `
                                <option value="${model.id}" ${config.ai_model_id === model.id ? 'selected' : ''}>
                                    ${model.name}
                                </option>
                            `).join('')}
                        </select>
                    </div>
                </div>

                <div class="form-actions" style="margin-top: 20px; text-align: right;">
                    <button type="button" class="btn btn-secondary" onclick="Modal.hide()">Cancel</button>
                    <button type="submit" class="btn btn-primary">Save Changes</button>
                </div>
            </form>
        `;

        Modal.show({
            title: 'Configure Schedule',
            content: modalContent,
            size: 'large'
        });

        const useAiCheckbox = document.getElementById('edit-use-ai');
        const aiOptions = document.getElementById('edit-ai-options');

        useAiCheckbox.addEventListener('change', (e) => {
            aiOptions.style.display = e.target.checked ? 'block' : 'none';
        });

        document.getElementById('edit-schedule-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            await updateSchedule(configId);
        });

    } catch (error) {
        console.error('Error showing config modal:', error);
        Toast.error('Failed to load configuration');
    }
}

async function updateSchedule(configId) {
    try {
        const reportType = document.getElementById('edit-report-type').value;
        const useAi = document.getElementById('edit-use-ai').checked;
        const aiModelId = useAi ? parseInt(document.getElementById('edit-ai-model').value) : null;

        const data = {
            report_type: reportType,
            use_ai_analysis: useAi,
            ai_model_id: aiModelId
        };

        await API.updateScheduledReportConfig(configId, data);
        Toast.success('Configuration updated successfully');
        Modal.hide();
        await loadConfigs();

    } catch (error) {
        console.error('Error updating schedule:', error);
        Toast.error(error.message || 'Failed to update configuration');
    }
}

async function showHistoryModal(datasourceId) {
    try {
        const history = await API.getScheduledReportHistory(datasourceId);

        const modalContent = `
            <h2>Report Generation History</h2>
            <div class="history-table-container">
                <table class="history-table">
                    <thead>
                        <tr>
                            <th>Scheduled Time</th>
                            <th>Actual Time</th>
                            <th>Duration</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${history.length === 0 ? `
                            <tr><td colspan="5" class="text-center">No history found</td></tr>
                        ` : history.map(h => `
                            <tr>
                                <td>${formatDateTime(h.scheduled_time)}</td>
                                <td>${h.actual_generation_time ? formatDateTime(h.actual_generation_time) : '-'}</td>
                                <td>${h.generation_duration_seconds ? h.generation_duration_seconds.toFixed(2) + 's' : '-'}</td>
                                <td>
                                    <span class="status-badge status-${h.status}" title="${h.skip_reason || h.error_message || ''}">
                                        ${h.status}
                                    </span>
                                </td>
                                <td>
                                    ${h.report_id ? `
                                        <button class="btn btn-sm btn-secondary" onclick="window.scheduledReports.viewReport(${h.report_id})">
                                            View Report
                                        </button>
                                    ` : '-'}
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;

        Modal.show({
            title: 'Report Generation History',
            content: modalContent,
            size: 'large'
        });

    } catch (error) {
        console.error('Error showing history:', error);
        Toast.error('Failed to load history');
    }
}

async function triggerNow(datasourceId) {
    if (!confirm('Trigger report generation now?')) return;

    try {
        await API.triggerScheduledReport(datasourceId);
        Toast.success('Report generation triggered');
        setTimeout(() => loadConfigs(), 2000);
    } catch (error) {
        console.error('Error triggering report:', error);
        Toast.error(error.message || 'Failed to trigger report');
    }
}

async function toggleEnabled(configId, enabled) {
    try {
        if (enabled) {
            await API.enableScheduledReport(configId);
            Toast.success('Schedule enabled');
        } else {
            await API.disableScheduledReport(configId);
            Toast.success('Schedule disabled');
        }
        await loadConfigs();
    } catch (error) {
        console.error('Error toggling schedule:', error);
        Toast.error(error.message || 'Failed to update schedule');
    }
}

async function viewReport(reportId) {
    try {
        // Close the history modal first
        Modal.hide();

        // Navigate to reports page
        window.location.hash = '#/reports';

        // Wait a bit for the page to load, then show the report
        setTimeout(async () => {
            const report = await API.getReport(reportId);
            if (ReportsPage._viewReport) {
                ReportsPage._viewReport(report);
            }
        }, 300);
    } catch (error) {
        console.error('Error viewing report:', error);
        Toast.error('Failed to load report');
    }
}

// Export functions to window for onclick handlers
window.scheduledReports = {
    showNewScheduleModal,
    showConfigModal,
    showHistoryModal,
    triggerNow,
    toggleEnabled,
    viewReport
};
