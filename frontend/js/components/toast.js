/* Toast notification component */
const Toast = {
    show(message, type = 'info', duration = 4000) {
        const container = DOM.$('#toast-container');
        const toast = DOM.el('div', { className: `toast ${type}` },
            DOM.el('span', { textContent: message }),
            DOM.el('button', {
                className: 'toast-close',
                textContent: '×',
                onClick: () => toast.remove()
            })
        );
        container.appendChild(toast);
        setTimeout(() => {
            if (toast.parentNode) {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(100%)';
                toast.style.transition = 'all 0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }
        }, duration);
    },

    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error', 6000); },
    warning(msg) { this.show(msg, 'warning'); },
    info(msg) { this.show(msg, 'info'); },
};
