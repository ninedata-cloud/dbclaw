/* Data table component powered by AG Grid Community Edition */
const DataTable = {
    _grids: [],

    create(columns, rows, options = {}) {
        const id = 'datatable-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
        const container = DOM.el('div', {
            id,
            className: 'data-table-wrapper',
            style: 'height: 100%; width: 100%; display: none;'
        });

        // AG Grid requires the element to be in the DOM before createGrid().
        // Keep it hidden until the grid is ready, then show it.
        document.body.appendChild(container);

        // Build column definitions
        const colDefs = columns.map(col => ({
            field: col,
            headerName: col,
            sortable: true,
            resizable: true,
            minWidth: 80,
            filter: options.enableFilter === true,
            cellStyle: params => {
                if (params.value === null || params.value === undefined) {
                    return { color: 'var(--text-muted)', fontStyle: 'italic' };
                }
                if (typeof params.value === 'number' && params.value > 9999) {
                    return { textAlign: 'right' };
                }
                return null;
            },
            valueFormatter: params => {
                if (params.value === null || params.value === undefined) {
                    return 'NULL';
                }
                if (typeof params.value === 'number' && params.value > 9999) {
                    return I18n.formatNumber(params.value);
                }
                return String(params.value);
            },
        }));

        const rowData = rows.map((row, idx) => {
            const rowObj = { _id: idx };
            columns.forEach((col, i) => {
                rowObj[col] = row[i];
            });
            return rowObj;
        });

        const gridOptions = {
            columnDefs: colDefs,
            rowData: rowData,
            defaultColDef: {
                sortable: true,
                resizable: true,
                minWidth: 80,
                filter: options.enableFilter === true,
            },
            rowBuffer: 20,
            rowModelType: 'clientSide',
            animateRows: true,
            rowSelection: options.multiRow ? 'multiple' : 'single',
            suppressRowClickSelection: false,
            enableCellTextSelection: true,
            copyHeadersToClipboard: false,
            domLayout: 'normal',
            headerHeight: options.headerHeight || 40,
            rowHeight: 36,
            floatingFilter: options.enableFilter === true && options.enableFloatingFilter === true,
            suppressContextMenu: false,
            theme: 'legacy',
            pagination: options.pagination === true,
            paginationPageSize: options.paginationPageSize || 100,
            paginationPageSizeSelector: [50, 100, 500, 1000],
            localeText: {
                page: I18n.t('dataTable.page'), more: I18n.t('dataTable.more'), to: I18n.t('dataTable.to'),
                of: I18n.t('dataTable.of'), next: I18n.t('dataTable.next'), last: I18n.t('dataTable.last'),
                first: I18n.t('dataTable.first'), previous: I18n.t('dataTable.previous'),
                loadingOoo: I18n.t('dataTable.loading'), noRowsToShow: I18n.t('dataTable.noRows'),
                searchOoo: I18n.t('dataTable.search'), blanks: I18n.t('dataTable.blanks'),
                filterOoo: I18n.t('dataTable.filter')
            },
            licenseKey: '',
            // onGridReady: reveal the grid once it's fully initialized
            onGridReady: () => {
                container.style.display = '';
            },
        };

        if (typeof agGrid === 'undefined') {
            console.error('[DataTable] agGrid not loaded!');
            container.style.display = '';
            container.innerHTML = `<div style="padding:20px;color:var(--accent-red)">${I18n.t('dataTable.gridUnavailable')}</div>`;
            return container;
        }

        const gridEl = document.getElementById(id);
        if (!gridEl) {
            console.error('[DataTable] container element not found:', id);
            return container;
        }

        try {
            agGrid.createGrid(gridEl, gridOptions);
            this._grids.push(id);
        } catch (err) {
            console.error('[DataTable] agGrid.createGrid failed:', err);
            container.style.display = '';
            container.innerHTML = `<div style="padding:20px;color:var(--accent-red)">${I18n.t('dataTable.renderFailed', { message: Utils.escapeHtml(err.message) })}</div>`;
        }

        return container;
    },

    destroy() {
        this._grids.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                agGrid.destroyGrid(id);
            }
        });
        this._grids = [];
    }
};
