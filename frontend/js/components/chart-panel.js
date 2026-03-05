/* Chart panel component using Chart.js */
const ChartPanel = {
    charts: {},

    create(id, title, type = 'line', options = {}) {
        const panel = DOM.el('div', { className: 'chart-panel', id: `chart-panel-${id}` });
        const header = DOM.el('div', { className: 'chart-panel-header' });
        header.appendChild(DOM.el('span', { className: 'chart-panel-title', textContent: title }));
        header.appendChild(DOM.el('span', { className: 'chart-panel-value', id: `chart-value-${id}`, textContent: '--' }));
        panel.appendChild(header);

        const container = DOM.el('div', { className: 'chart-container' });
        const canvas = DOM.el('canvas', { id: `chart-${id}` });
        container.appendChild(canvas);
        panel.appendChild(container);

        return panel;
    },

    init(id, type = 'line', config = {}) {
        const canvas = document.getElementById(`chart-${id}`);
        if (!canvas) return;

        const defaultConfig = {
            type,
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    borderColor: '#2f81f7',
                    backgroundColor: 'rgba(47, 129, 247, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 0,
                    pointHitRadius: 10,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 300 },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#1c2333',
                        borderColor: '#2a3140',
                        borderWidth: 1,
                        titleColor: '#e6edf3',
                        bodyColor: '#8b949e',
                        padding: 10,
                        cornerRadius: 6,
                    }
                },
                scales: {
                    x: {
                        display: true,
                        grid: { color: 'rgba(42,49,64,0.5)', drawBorder: false },
                        ticks: { color: '#6e7681', font: { size: 10 }, maxTicksLimit: 6 },
                    },
                    y: {
                        display: true,
                        grid: { color: 'rgba(42,49,64,0.5)', drawBorder: false },
                        ticks: { color: '#6e7681', font: { size: 10 }, maxTicksLimit: 5 },
                        beginAtZero: true,
                    }
                },
                interaction: { intersect: false, mode: 'index' },
            }
        };

        // Deep merge config
        const merged = this._deepMerge(defaultConfig, config);
        this.charts[id] = new Chart(canvas, merged);
        return this.charts[id];
    },

    update(id, label, value, maxPoints = 30) {
        const chart = this.charts[id];
        if (!chart) return;

        chart.data.labels.push(label);
        chart.data.datasets[0].data.push(value);

        if (chart.data.labels.length > maxPoints) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
        }

        chart.update('none');

        // Update value display
        const valueEl = document.getElementById(`chart-value-${id}`);
        if (valueEl) {
            valueEl.textContent = typeof value === 'number' ? value.toLocaleString() : value;
        }
    },

    destroy(id) {
        if (this.charts[id]) {
            this.charts[id].destroy();
            delete this.charts[id];
        }
    },

    destroyAll() {
        for (const id of Object.keys(this.charts)) {
            this.destroy(id);
        }
    },

    _deepMerge(target, source) {
        const result = { ...target };
        for (const key of Object.keys(source)) {
            if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
                result[key] = this._deepMerge(result[key] || {}, source[key]);
            } else {
                result[key] = source[key];
            }
        }
        return result;
    }
};
