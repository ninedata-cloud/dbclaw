/* Formatting utilities */
const Format = {
    parseDate(value) {
        if (!value) return null;
        if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
        if (typeof value === 'number') {
            const dateFromNumber = new Date(value);
            return Number.isNaN(dateFromNumber.getTime()) ? null : dateFromNumber;
        }

        if (typeof value !== 'string') return null;
        const raw = value.trim();
        if (!raw) return null;
        if (/^\d+$/.test(raw)) {
            const ts = Number(raw);
            if (Number.isFinite(ts)) {
                const normalizedTs = raw.length === 10 ? ts * 1000 : ts;
                const dateFromTs = new Date(normalizedTs);
                if (!Number.isNaN(dateFromTs.getTime())) return dateFromTs;
            }
        }

        let normalized = raw.replace(' ', 'T');
        normalized = normalized.replace(/(\.\d{3})\d+/, '$1');
        normalized = normalized.replace(/([+-]\d{2})(\d{2})$/, '$1:$2');
        normalized = normalized.replace(/([+-]\d{2})$/, '$1:00');
        normalized = normalized.replace(/UTC$/i, 'Z');
        normalized = normalized.replace(/ GMT$/i, 'Z');
        normalized = normalized.replace(/([+-]\d{2}:\d{2})Z$/i, '$1');
        normalized = normalized.replace(/([+-]\d{2})Z$/i, '$1:00');

        const parsed = new Date(normalized);
        if (!Number.isNaN(parsed.getTime())) return parsed;

        const match = raw.match(
            /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:\.(\d+))?(?:\s*(Z|UTC|[+-]\d{2}(?::?\d{2})?))?$/i
        );
        if (match) {
            const year = Number(match[1]);
            const month = Number(match[2]) - 1;
            const day = Number(match[3]);
            const hour = Number(match[4]);
            const minute = Number(match[5]);
            const second = Number(match[6] || 0);
            const millisecond = Number((match[7] || '0').slice(0, 3).padEnd(3, '0'));
            const tz = (match[8] || '').toUpperCase();
            let offsetMinutes = null;

            if (!tz || tz === 'Z' || tz === 'UTC') {
                offsetMinutes = 0;
            } else {
                const tzMatch = tz.match(/^([+-])(\d{2})(?::?(\d{2}))?$/);
                if (tzMatch) {
                    const sign = tzMatch[1] === '-' ? -1 : 1;
                    const tzHours = Number(tzMatch[2]);
                    const tzMinutes = Number(tzMatch[3] || 0);
                    offsetMinutes = sign * (tzHours * 60 + tzMinutes);
                }
            }

            if (offsetMinutes !== null) {
                const utcMs = Date.UTC(year, month, day, hour, minute, second, millisecond) - offsetMinutes * 60 * 1000;
                const manual = new Date(utcMs);
                if (!Number.isNaN(manual.getTime())) return manual;
            }
        }

        const fallback = new Date(raw);
        return Number.isNaN(fallback.getTime()) ? null : fallback;
    },

    bytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(Math.abs(bytes)) / Math.log(1024));
        return parseFloat((bytes / Math.pow(1024, i)).toFixed(1)) + ' ' + units[i];
    },

    networkRate(bytesPerSecond) {
        if (bytesPerSecond === null || bytesPerSecond === undefined) return '--';

        const value = typeof bytesPerSecond === 'number'
            ? bytesPerSecond
            : parseFloat(bytesPerSecond);

        if (Number.isNaN(value)) return '--';

        const absolute = Math.abs(value);
        if (absolute >= 1024 * 1024) {
            return (value / (1024 * 1024)).toFixed(2) + ' MB/s';
        }
        if (absolute >= 1024) {
            return (value / 1024).toFixed(2) + ' KB/s';
        }
        return Math.round(value) + ' Bytes/s';
    },

    number(num) {
        if (num === null || num === undefined) return '0';
        if (typeof num !== 'number') num = parseFloat(num) || 0;
        if (num >= 1e9) return (num / 1e9).toFixed(1) + 'B';
        if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
        if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
        return num.toLocaleString();
    },

    percent(value) {
        if (value === null || value === undefined) return '0%';
        return parseFloat(value).toFixed(1) + '%';
    },

    duration(ms) {
        if (ms < 1) return '<1ms';
        if (ms < 1000) return Math.round(ms) + 'ms';
        if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
        return (ms / 60000).toFixed(1) + 'min';
    },

    timeAgo(dateStr) {
        const date = Format.parseDate(dateStr);
        if (!date) return 'N/A';
        const now = new Date();
        const seconds = Math.floor((now - date) / 1000);
        if (Number.isNaN(seconds) || seconds < 0) return 'N/A';
        if (seconds < 60) return 'just now';
        if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
        if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
        return Math.floor(seconds / 86400) + 'd ago';
    },

    datetime(dateStr) {
        const date = Format.parseDate(dateStr);
        if (!date) return typeof dateStr === 'string' && dateStr.trim() ? dateStr : 'N/A';
        return date.toLocaleString();
    },

    uptime(seconds) {
        if (seconds === null || seconds === undefined) return 'N/A';
        seconds = Math.floor(seconds);
        if (seconds < 0) return 'N/A';
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        if (days > 0) return `${days}d ${hours}h`;
        if (hours > 0) return `${hours}h ${mins}m`;
        if (mins > 0) return `${mins}m`;
        return `${seconds}s`;
    }
};

/* Utils namespace for compatibility */
const Utils = {
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    formatDate(dateStr) {
        return Format.datetime(dateStr);
    },

    formatFileSize(bytes) {
        return Format.bytes(bytes);
    },

    showToast(message, type = 'info') {
        Toast.show(message, type);
    }
};
