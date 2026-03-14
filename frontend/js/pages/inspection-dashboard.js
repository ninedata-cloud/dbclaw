import { API_BASE_URL } from '../api.js';

let currentDatasourceId = null;
let currentConfig = null;

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadDatasources();
    setupEventListeners();
});

function setupEventListeners() {
    document.getElementById('datasourceSelect').addEventListener('change', onDatasourceChange);
    document.getElementById('manualInspectBtn').addEventListener('click', triggerManualInspection);
    document.getElementById('configBtn').addEventListener('click', showConfigPanel);
    document.getElementById('saveConfigBtn').addEventListener('click', saveConfig);
    document.getElementById('cancelConfigBtn').addEventListener('click', hideConfigPanel);
    document.querySelector('.close').addEventListener('click', closeModal);
}

async function loadDatasources() {
    try {
        const response = await fetch(`${API_BASE_URL}/datasources`);
        const datasources = await response.json();
        const select = document.getElementById('datasourceSelect');
        datasources.forEach(ds => {
            const option = document.createElement('option');
            option.value = ds.id;
            option.textContent = `${ds.name} (${ds.db_type})`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load datasources:', error);
    }
}

async function onDatasourceChange(e) {
    currentDatasourceId = e.target.value;
    if (currentDatasourceId) {
        document.getElementById('manualInspectBtn').disabled = false;
        document.getElementById('configBtn').disabled = false;
        await loadConfig();
        await loadReports();
    } else {
        document.getElementById('manualInspectBtn').disabled = true;
        document.getElementById('configBtn').disabled = true;
    }
}

async function loadConfig() {
    try {
        const response = await fetch(`${API_BASE_URL}/inspections/config/${currentDatasourceId}`);
        currentConfig = await response.json();
        document.getElementById('enabledCheck').checked = currentConfig.enabled;
        document.getElementById('scheduleInterval').value = currentConfig.schedule_interval;
        document.getElementById('useAiCheck').checked = currentConfig.use_ai_analysis;
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

async function loadReports() {
    try {
        const response = await fetch(`${API_BASE_URL}/inspections/reports/${currentDatasourceId}?limit=20`);
        const reports = await response.json();
        const container = document.getElementById('reports');
        container.innerHTML = reports.map(r => `
            <div class="report-item" onclick="viewReport(${r.report_id})">
                <span class="badge ${r.trigger_type}">${getBadge(r.trigger_type)}</span>
                <strong>${r.title}</strong>
                <span>${r.created_at}</span>
                ${r.trigger_reason ? `<div class="reason">${r.trigger_reason}</div>` : ''}
            </div>
        `).join('');
    } catch (error) {
        console.error('Failed to load reports:', error);
    }
}

function getBadge(type) {
    const badges = { anomaly: '🔴 Anomaly', scheduled: '📅 Scheduled', manual: '👤 Manual' };
    return badges[type] || type;
}

async function triggerManualInspection() {
    try {
        const response = await fetch(`${API_BASE_URL}/inspections/trigger/${currentDatasourceId}`, { method: 'POST' });
        const result = await response.json();
        alert('Inspection triggered successfully!');
        await loadReports();
    } catch (error) {
        console.error('Failed to trigger inspection:', error);
        alert('Failed to trigger inspection');
    }
}

function showConfigPanel() {
    document.getElementById('configPanel').style.display = 'block';
}

function hideConfigPanel() {
    document.getElementById('configPanel').style.display = 'none';
}

async function saveConfig() {
    try {
        const config = {
            enabled: document.getElementById('enabledCheck').checked,
            schedule_interval: parseInt(document.getElementById('scheduleInterval').value),
            use_ai_analysis: document.getElementById('useAiCheck').checked,
            threshold_rules: currentConfig.threshold_rules,
            anomaly_check_enabled: currentConfig.anomaly_check_enabled,
            anomaly_diagnosis_interval: currentConfig.anomaly_diagnosis_interval,
            ai_model_id: currentConfig.ai_model_id,
            kb_ids: currentConfig.kb_ids
        };
        await fetch(`${API_BASE_URL}/inspections/config/${currentDatasourceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        alert('Configuration saved!');
        hideConfigPanel();
    } catch (error) {
        console.error('Failed to save config:', error);
        alert('Failed to save configuration');
    }
}

window.viewReport = async function(reportId) {
    try {
        const response = await fetch(`${API_BASE_URL}/inspections/reports/detail/${reportId}`);
        const report = await response.json();
        const modal = document.getElementById('reportModal');
        const content = document.getElementById('reportContent');

        // Add export buttons
        const exportButtons = `
            <div style="margin-bottom: 20px; text-align: right;">
                <button onclick="exportMarkdown(${reportId})" class="btn btn-secondary" style="margin-right: 10px;">
                    📄 导出 Markdown
                </button>
                <button onclick="exportPDF(${reportId})" class="btn btn-primary">
                    📑 导出 PDF
                </button>
            </div>
        `;

        content.innerHTML = exportButtons + MarkdownRenderer.render(report.content_md);
        modal.style.display = 'block';
    } catch (error) {
        console.error('Failed to load report:', error);
    }
}

window.exportMarkdown = function(reportId) {
    window.open(`${API_BASE_URL}/inspections/reports/export/${reportId}/markdown`, '_blank');
}

window.exportPDF = function(reportId) {
    window.open(`${API_BASE_URL}/inspections/reports/export/${reportId}/pdf`, '_blank');
}

function closeModal() {
    document.getElementById('reportModal').style.display = 'none';
}

