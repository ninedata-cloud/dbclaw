/* Simple pub/sub state store */
const Store = {
    _state: {
        connections: [],
        currentConnection: null,
        currentInstance: null,
        currentInstanceId: null,
        currentPage: 'dashboard',
        hosts: [],
        chatSessions: [],
        currentSession: null,
    },
    _listeners: {},

    get(key) {
        return this._state[key];
    },

    set(key, value) {
        this._state[key] = value;
        this._notify(key, value);
    },

    subscribe(key, callback) {
        if (!this._listeners[key]) this._listeners[key] = [];
        this._listeners[key].push(callback);
        return () => {
            this._listeners[key] = this._listeners[key].filter(cb => cb !== callback);
        };
    },

    _notify(key, value) {
        if (this._listeners[key]) {
            for (const cb of this._listeners[key]) {
                try { cb(value); } catch (e) { console.error('Store listener error:', e); }
            }
        }
    }
};
