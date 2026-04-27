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
        if (!canvas) {
            console.error(`[ChartPanel] Canvas not found for chart: ${id}`);
            return null;
        }

        // Check if Chart is available
        if (typeof Chart === 'undefined') {
            console.error('[ChartPanel] Chart.js is not loaded!');
            return null;
        }

        // If chart already exists, destroy it first
        if (this.charts[id]) {
            console.log(`[ChartPanel] Destroying existing chart: ${id}`);
            this.charts[id].destroy();
        }

        console.log(`[ChartPanel] Initializing chart: ${id}`);

        const defaultConfig = {
            type,
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    borderColor: '#2f81f7',
                    backgroundColor: 'rgba(47, 129, 247, 0.1)',
                    borderWidth: 1,
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
        const valueFormatter = merged.valueFormatter;
        delete merged.valueFormatter;

        try {
            this.charts[id] = new Chart(canvas, merged);
            if (typeof valueFormatter === 'function') {
                this.charts[id]._valueFormatter = valueFormatter;
            }
            console.log(`[ChartPanel] Chart ${id} initialized successfully`);
            return this.charts[id];
        } catch (error) {
            console.error(`[ChartPanel] Failed to initialize chart ${id}:`, error);
            return null;
        }
    },

    update(id, label, value, maxPoints = 30) {
        const chart = this.charts[id];
        if (!chart) {
            console.error(`[ChartPanel] Chart not found: ${id}. Available charts:`, Object.keys(this.charts));
            return;
        }

        chart.data.labels.push(label);

        // Support both single value and multiple values (for multi-line charts)
        if (Array.isArray(value)) {
            // Multiple datasets
            value.forEach((val, idx) => {
                if (chart.data.datasets[idx]) {
                    chart.data.datasets[idx].data.push(val);
                }
            });
        } else {
            // Single dataset
            chart.data.datasets[0].data.push(value);
        }

        if (chart.data.labels.length > maxPoints) {
            chart.data.labels.shift();
            chart.data.datasets.forEach(dataset => {
                dataset.data.shift();
            });
        }

        chart.update('none');

        // Update value display
        const valueEl = document.getElementById(`chart-value-${id}`);
        if (valueEl) {
            if (typeof chart._valueFormatter === 'function') {
                valueEl.textContent = chart._valueFormatter(value);
            } else if (Array.isArray(value)) {
                valueEl.textContent = value.map(v =>
                    typeof v === 'number' ? v.toLocaleString() : v
                ).join(' / ');
            } else {
                valueEl.textContent = typeof value === 'number' ? value.toLocaleString() : value;
            }
        }
    },

    batchUpdate(id, labels, values, maxPoints = 30) {
        const chart = this.charts[id];
        if (!chart) {
            console.error(`[ChartPanel] Chart not found: ${id}. Available charts:`, Object.keys(this.charts));
            return;
        }

        // Replace all data at once
        chart.data.labels = labels.slice(-maxPoints);
        chart.data.datasets[0].data = values.slice(-maxPoints);

        // Update chart without animation for better performance
        chart.update('none');

        // Update value display with latest value
        const valueEl = document.getElementById(`chart-value-${id}`);
        if (valueEl && values.length > 0) {
            const latestValue = values[values.length - 1];
            if (typeof chart._valueFormatter === 'function') {
                valueEl.textContent = chart._valueFormatter(latestValue);
            } else {
                valueEl.textContent = typeof latestValue === 'number' ? latestValue.toLocaleString() : latestValue;
            }
        }
    },

    batchUpdateMulti(id, labels, valuesArray, maxPoints = 30) {
        const chart = this.charts[id];
        if (!chart) {
            console.error(`[ChartPanel] Chart not found: ${id}. Available charts:`, Object.keys(this.charts));
            return;
        }

        // Replace all data at once for multiple datasets
        chart.data.labels = labels.slice(-maxPoints);
        valuesArray.forEach((values, idx) => {
            if (chart.data.datasets[idx]) {
                chart.data.datasets[idx].data = values.slice(-maxPoints);
            }
        });

        // Update chart without animation for better performance
        chart.update('none');

        // Update value display with latest values
        const valueEl = document.getElementById(`chart-value-${id}`);
        if (valueEl && valuesArray.length > 0) {
            const latestValues = valuesArray.map(arr => (arr.length ? arr[arr.length - 1] : null));
            if (typeof chart._valueFormatter === 'function') {
                valueEl.textContent = chart._valueFormatter(latestValues);
            } else {
                valueEl.textContent = latestValues.map(v =>
                    typeof v === 'number' ? v.toLocaleString() : v
                ).join(' / ');
            }
        }
    },

    clear(id) {
        const chart = this.charts[id];
        if (!chart) {
            console.error(`[ChartPanel] Chart not found: ${id}`);
            return;
        }

        // Clear all data
        chart.data.labels = [];
        chart.data.datasets.forEach(dataset => {
            dataset.data = [];
        });

        chart.update('none');

        // Clear value display
        const valueEl = document.getElementById(`chart-value-${id}`);
        if (valueEl) {
            valueEl.textContent = '--';
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
