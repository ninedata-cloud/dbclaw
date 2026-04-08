/**
 * Schema Cache Manager
 * Caches database schema metadata for autocomplete with 5-minute TTL
 */

const SchemaCache = {
    cache: new Map(),
    TTL: 5 * 60 * 1000, // 5 minutes

    _getCacheKey(datasourceId, type, params = {}) {
        return `${datasourceId}:${type}:${JSON.stringify(params)}`;
    },

    _isExpired(entry) {
        return Date.now() - entry.timestamp > this.TTL;
    },

    async getSchemas(datasourceId, options = {}) {
        const key = this._getCacheKey(datasourceId, 'schemas', options);
        const cached = this.cache.get(key);

        if (cached && !this._isExpired(cached)) {
            return cached.data;
        }

        try {
            const data = await API.getSchemas(datasourceId, options);
            this.cache.set(key, { data, timestamp: Date.now() });
            return data;
        } catch (error) {
            console.error('Error fetching schemas:', error);
            return [];
        }
    },

    async getTables(datasourceId, options = {}) {
        const key = this._getCacheKey(datasourceId, 'tables', options);
        const cached = this.cache.get(key);

        if (cached && !this._isExpired(cached)) {
            return cached.data;
        }

        try {
            const data = await API.getTables(datasourceId, options);
            this.cache.set(key, { data, timestamp: Date.now() });
            return data;
        } catch (error) {
            console.error('Error fetching tables:', error);
            return [];
        }
    },

    async getColumns(datasourceId, table, options = {}) {
        const key = this._getCacheKey(datasourceId, 'columns', { table, ...options });
        const cached = this.cache.get(key);

        if (cached && !this._isExpired(cached)) {
            return cached.data;
        }

        try {
            const data = await API.getColumns(datasourceId, table, options);
            this.cache.set(key, { data, timestamp: Date.now() });
            return data;
        } catch (error) {
            console.error('Error fetching columns:', error);
            return [];
        }
    },

    invalidate(datasourceId) {
        // Remove all cache entries for this datasource
        for (const key of this.cache.keys()) {
            if (key.startsWith(`${datasourceId}:`)) {
                this.cache.delete(key);
            }
        }
    },

    clear() {
        this.cache.clear();
    }
};

window.SchemaCache = SchemaCache;
