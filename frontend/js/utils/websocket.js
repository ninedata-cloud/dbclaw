/* WebSocket manager */
class WSManager {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.listeners = new Map();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;
        this.shouldReconnect = true;
    }

    connect() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) return;

        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${location.host}${this.url}`;
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.reconnectAttempts = 0;
            this._emit('open');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this._emit('message', data);
            } catch (e) {
                this._emit('message', event.data);
            }
        };

        this.ws.onclose = (event) => {
            this._emit('close', event);
            if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                setTimeout(() => this.connect(), this.reconnectDelay * this.reconnectAttempts);
            }
        };

        this.ws.onerror = (error) => {
            this._emit('error', error);
        };
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(typeof data === 'string' ? data : JSON.stringify(data));
        }
    }

    on(event, callback) {
        if (!this.listeners.has(event)) this.listeners.set(event, []);
        this.listeners.get(event).push(callback);
        return this;
    }

    off(event, callback) {
        if (this.listeners.has(event)) {
            const cbs = this.listeners.get(event).filter(cb => cb !== callback);
            this.listeners.set(event, cbs);
        }
    }

    _emit(event, data) {
        if (this.listeners.has(event)) {
            for (const cb of this.listeners.get(event)) cb(data);
        }
    }

    disconnect() {
        this.shouldReconnect = false;
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}
