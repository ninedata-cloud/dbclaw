/* Data table component */
const DataTable = {
    create(columns, rows, options = {}) {
        const container = DOM.el('div', { className: 'data-table-container' });
        const table = DOM.el('table', { className: 'data-table' });

        // Header
        const thead = DOM.el('thead');
        const headerRow = DOM.el('tr');
        for (const col of columns) {
            headerRow.appendChild(DOM.el('th', { textContent: col }));
        }
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Body
        const tbody = DOM.el('tbody');
        if (rows.length === 0) {
            const emptyRow = DOM.el('tr');
            emptyRow.appendChild(DOM.el('td', {
                textContent: 'No data',
                colSpan: columns.length,
                style: { textAlign: 'center', color: 'var(--text-muted)', padding: '24px' }
            }));
            tbody.appendChild(emptyRow);
        } else {
            for (const row of rows) {
                const tr = DOM.el('tr');
                for (const cell of row) {
                    const td = DOM.el('td');
                    if (cell === null || cell === undefined) {
                        td.textContent = 'NULL';
                        td.style.color = 'var(--text-muted)';
                        td.style.fontStyle = 'italic';
                    } else {
                        td.textContent = String(cell);
                        td.title = String(cell);
                    }
                    tr.appendChild(td);
                }
                tbody.appendChild(tr);
            }
        }
        table.appendChild(tbody);
        container.appendChild(table);
        return container;
    }
};
