/* DOM utility helpers */
const DOM = {
    el(tag, attrs = {}, ...children) {
        const element = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs)) {
            if (key === 'className') element.className = value;
            else if (key === 'innerHTML') element.innerHTML = value;
            else if (key === 'textContent') element.textContent = value;
            else if (key.startsWith('on')) element.addEventListener(key.slice(2).toLowerCase(), value);
            else if (key === 'style' && typeof value === 'object') Object.assign(element.style, value);
            else if (key === 'dataset') Object.assign(element.dataset, value);
            else element.setAttribute(key, value);
        }
        for (const child of children) {
            if (typeof child === 'string') element.appendChild(document.createTextNode(child));
            else if (child instanceof Node) element.appendChild(child);
        }
        return element;
    },

    $(selector, parent = document) {
        return parent.querySelector(selector);
    },

    $$(selector, parent = document) {
        return Array.from(parent.querySelectorAll(selector));
    },

    clear(element) {
        element.innerHTML = '';
    },

    show(element) {
        element.classList.remove('hidden');
    },

    hide(element) {
        element.classList.add('hidden');
    },

    toggle(element, show) {
        element.classList.toggle('hidden', !show);
    }
};
