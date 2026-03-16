/* Modal component */
const Modal = {
    show({ title, content, buttons, footer, size = 'medium', width }) {
        const overlay = DOM.$('#modal-overlay');
        const container = DOM.$('#modal-container');

        const sizes = { small: '400px', medium: '600px', large: '800px' };
        container.style.maxWidth = width || sizes[size] || sizes.medium;

        container.innerHTML = '';
        const header = DOM.el('div', { className: 'modal-header' },
            DOM.el('h3', { className: 'modal-title', textContent: title }),
            DOM.el('button', {
                className: 'btn-icon',
                innerHTML: '<i data-lucide="x"></i>',
                onClick: () => this.hide()
            })
        );
        container.appendChild(header);

        const body = DOM.el('div', { className: 'modal-body' });
        if (typeof content === 'string') body.innerHTML = content;
        else if (content instanceof Node) body.appendChild(content);
        container.appendChild(body);

        if (footer) {
            if (footer instanceof Node) {
                container.appendChild(footer);
            }
        } else if (buttons && buttons.length > 0) {
            const footerEl = DOM.el('div', { className: 'modal-footer' });
            buttons.forEach(btn => {
                const button = DOM.el('button', {
                    className: `btn btn-${btn.variant || 'secondary'}`,
                    textContent: btn.text,
                    onClick: btn.onClick
                });
                footerEl.appendChild(button);
            });
            container.appendChild(footerEl);
        }

        DOM.show(overlay);
        DOM.createIcons();
    },

    hide() {
        const overlay = DOM.$('#modal-overlay');
        DOM.hide(overlay);
        overlay.onclick = null;
    }
};
