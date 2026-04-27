/* Metric card component */
const MetricCard = {
    create(label, value, change = null) {
        const card = DOM.el('div', { className: 'metric-card' });
        card.appendChild(DOM.el('div', { className: 'metric-card-label', textContent: label }));
        card.appendChild(DOM.el('div', { className: 'metric-card-value', textContent: value }));
        if (change !== null) {
            const changeClass = change >= 0 ? 'up' : 'down';
            const changeText = change >= 0 ? `+${change}` : `${change}`;
            card.appendChild(DOM.el('div', {
                className: `metric-card-change ${changeClass}`,
                textContent: changeText
            }));
        }
        return card;
    },

    update(element, value) {
        const valueEl = element.querySelector('.metric-card-value');
        if (valueEl) valueEl.textContent = value;
    }
};
