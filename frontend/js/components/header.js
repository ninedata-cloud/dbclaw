/* Header component */
const Header = {
    render(title, actions = null) {
        const header = DOM.$('#page-header');
        header.innerHTML = '';
        header.appendChild(DOM.el('h1', { textContent: title }));
        if (actions) {
            const actionsContainer = DOM.el('div', { className: 'flex gap-8' });
            if (typeof actions === 'string') actionsContainer.innerHTML = actions;
            else if (actions instanceof Node) actionsContainer.appendChild(actions);
            else if (Array.isArray(actions)) actions.forEach(a => actionsContainer.appendChild(a));
            header.appendChild(actionsContainer);
        }
        DOM.createIcons();
    }
};
