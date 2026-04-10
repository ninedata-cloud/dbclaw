/* Formatting utilities */
const Format = {
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
        if (!dateStr) return 'N/A';
        const date = new Date(dateStr);
        const now = new Date();
        const seconds = Math.floor((now - date) / 1000);
        if (seconds < 60) return 'just now';
        if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
        if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
        return Math.floor(seconds / 86400) + 'd ago';
    },

    datetime(dateStr) {
        if (!dateStr) return 'N/A';
        return new Date(dateStr).toLocaleString();
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
