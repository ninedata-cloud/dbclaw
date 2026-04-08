/**
 * SQL Autocomplete Provider for Monaco Editor
 * Provides context-aware SQL suggestions
 */

const SQL_KEYWORDS = [
    'SELECT', 'FROM', 'WHERE', 'JOIN', 'INNER', 'LEFT', 'RIGHT', 'OUTER', 'FULL',
    'ON', 'AND', 'OR', 'NOT', 'IN', 'LIKE', 'BETWEEN', 'IS', 'NULL',
    'ORDER', 'BY', 'GROUP', 'HAVING', 'LIMIT', 'OFFSET',
    'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE',
    'CREATE', 'TABLE', 'ALTER', 'DROP', 'INDEX', 'VIEW',
    'AS', 'DISTINCT', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX',
    'UNION', 'ALL', 'EXISTS', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
    'ASC', 'DESC', 'WITH', 'RECURSIVE'
];

class SQLCompletionProvider {
    constructor(datasourceId, schemaCache, context = {}) {
        this.datasourceId = datasourceId;
        this.schemaCache = schemaCache;
        this.database = context.database || null;
        this.schema = context.schema || null;
        this.schemas = [];
        this.tables = [];
        this.tableColumns = new Map();
    }

    async loadSchema() {
        try {
            console.log('[SQLCompletionProvider] Loading schema for datasource:', this.datasourceId);
            this.schemas = await this.schemaCache.getSchemas(this.datasourceId, {
                database: this.database,
            });
            console.log('[SQLCompletionProvider] Loaded schemas:', this.schemas);
            this.tables = await this.schemaCache.getTables(this.datasourceId, {
                database: this.database,
                schema: this.schema,
            });
            console.log('[SQLCompletionProvider] Loaded tables:', this.tables);
        } catch (error) {
            console.error('Error loading schema:', error);
        }
    }

    async provideCompletionItems(model, position) {
        console.log('[SQLCompletionProvider] provideCompletionItems called');
        const textUntilPosition = model.getValueInRange({
            startLineNumber: 1,
            startColumn: 1,
            endLineNumber: position.lineNumber,
            endColumn: position.column
        });

        const context = this._parseContext(textUntilPosition);
        console.log('[SQLCompletionProvider] Context:', context);

        const word = model.getWordUntilPosition(position);
        const range = {
            startLineNumber: position.lineNumber,
            endLineNumber: position.lineNumber,
            startColumn: word.startColumn,
            endColumn: word.endColumn
        };

        let suggestions = [];

        // Context-aware suggestions
        if (context.afterFrom || context.afterJoin) {
            // Suggest tables
            console.log('[SQLCompletionProvider] Suggesting tables');
            suggestions = this._getTableSuggestions(range);
        } else if (context.afterSelect || context.afterWhere) {
            // Suggest columns from tables in FROM clause
            console.log('[SQLCompletionProvider] Suggesting columns');
            suggestions = await this._getColumnSuggestions(range, context.tables);
        } else if (context.afterDot) {
            // Suggest columns for specific table
            const tableName = context.tableBeforeDot;
            console.log('[SQLCompletionProvider] Suggesting columns for table:', tableName);
            if (tableName) {
                suggestions = await this._getColumnsForTable(range, tableName);
            }
        } else {
            // Default: suggest keywords and tables
            console.log('[SQLCompletionProvider] Suggesting keywords and tables');
            suggestions = [
                ...this._getKeywordSuggestions(range),
                ...this._getTableSuggestions(range)
            ];
        }

        console.log('[SQLCompletionProvider] Returning', suggestions.length, 'suggestions');
        return { suggestions };
    }

    _parseContext(text) {
        const upperText = text.toUpperCase();
        const tokens = text.split(/\s+/);
        const lastToken = tokens[tokens.length - 1]?.toUpperCase() || '';
        const secondLastToken = tokens[tokens.length - 2]?.toUpperCase() || '';

        // Check for dot notation (table.column)
        const dotMatch = text.match(/(\w+)\.$/);
        const afterDot = !!dotMatch;
        const tableBeforeDot = dotMatch ? dotMatch[1] : null;

        // Extract tables from FROM clause
        const fromMatch = upperText.match(/FROM\s+([\w\s,]+?)(?:WHERE|JOIN|GROUP|ORDER|LIMIT|$)/i);
        const tables = fromMatch ? fromMatch[1].split(',').map(t => t.trim().split(/\s+/)[0]) : [];

        return {
            afterSelect: lastToken === 'SELECT' || (secondLastToken === 'SELECT' && lastToken === ','),
            afterFrom: lastToken === 'FROM',
            afterWhere: lastToken === 'WHERE' || (upperText.includes('WHERE') && lastToken === 'AND') || (upperText.includes('WHERE') && lastToken === 'OR'),
            afterJoin: lastToken === 'JOIN' || secondLastToken === 'JOIN',
            afterDot,
            tableBeforeDot,
            tables
        };
    }

    _getKeywordSuggestions(range) {
        return SQL_KEYWORDS.map(keyword => ({
            label: keyword,
            kind: monaco.languages.CompletionItemKind.Keyword,
            insertText: keyword,
            range: range
        }));
    }

    _getTableSuggestions(range) {
        console.log('[SQLCompletionProvider] Getting table suggestions, tables:', this.tables);
        return this.tables.map(table => ({
            label: table.name,
            kind: monaco.languages.CompletionItemKind.Class,
            insertText: table.name,
            detail: table.type || 'TABLE',
            documentation: table.comment || `Schema: ${table.schema || 'default'}`,
            range: range
        }));
    }

    async _getColumnSuggestions(range, tables) {
        const suggestions = [];

        // If no tables in context, return empty
        if (!tables || tables.length === 0) {
            return suggestions;
        }

        // Load columns for each table
        for (const tableName of tables) {
            const columns = await this._loadColumnsForTable(tableName);
            for (const col of columns) {
                suggestions.push({
                    label: col.name,
                    kind: monaco.languages.CompletionItemKind.Field,
                    insertText: col.name,
                    detail: `${col.type}${col.nullable ? ' (nullable)' : ''}`,
                    documentation: `Table: ${tableName}${col.comment ? '\n' + col.comment : ''}`,
                    range: range
                });
            }
        }

        return suggestions;
    }

    async _getColumnsForTable(range, tableName) {
        const columns = await this._loadColumnsForTable(tableName);
        return columns.map(col => ({
            label: col.name,
            kind: monaco.languages.CompletionItemKind.Field,
            insertText: col.name,
            detail: `${col.type}${col.nullable ? ' (nullable)' : ''}`,
            documentation: col.comment || '',
            range: range
        }));
    }

    async _loadColumnsForTable(tableName) {
        if (this.tableColumns.has(tableName)) {
            return this.tableColumns.get(tableName);
        }

        try {
            const columns = await this.schemaCache.getColumns(this.datasourceId, tableName, {
                database: this.database,
                schema: this.schema,
            });
            this.tableColumns.set(tableName, columns);
            return columns;
        } catch (error) {
            console.error(`Error loading columns for table ${tableName}:`, error);
            return [];
        }
    }

    setDatasource(datasourceId, context = {}) {
        this.datasourceId = datasourceId;
        this.database = context.database || null;
        this.schema = context.schema || null;
        this.schemas = [];
        this.tables = [];
        this.tableColumns.clear();
    }
}

window.SQLCompletionProvider = SQLCompletionProvider;
