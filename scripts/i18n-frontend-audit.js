#!/usr/bin/env node
/** AST based guard against new hard-coded user-visible frontend copy. */
const fs = require('node:fs');
const path = require('node:path');
const acorn = require('acorn');

const root = path.resolve(__dirname, '..');
const sourceRoot = path.join(root, 'frontend', 'js');
const hanPattern = /[\u3400-\u9fff]/u;
const asciiWordPattern = /[A-Za-z]{2,}/u;

function walkFiles(directory, output = []) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
        const target = path.join(directory, entry.name);
        if (entry.isDirectory()) {
            if (entry.name !== 'locales' && entry.name !== 'lib') walkFiles(target, output);
        } else if (entry.name.endsWith('.js')) {
            output.push(target);
        }
    }
    return output;
}

function walk(node, visitor, parents = []) {
    if (!node || typeof node !== 'object') return;
    if (typeof node.type === 'string') visitor(node, parents);
    const nextParents = typeof node.type === 'string' ? [...parents, node] : parents;
    for (const [key, value] of Object.entries(node)) {
        if (key === 'start' || key === 'end' || key === 'loc') continue;
        if (Array.isArray(value)) value.forEach(child => walk(child, visitor, nextParents));
        else if (value && typeof value === 'object') walk(value, visitor, nextParents);
    }
}

function calleeName(call) {
    if (!call || call.type !== 'CallExpression') return '';
    const callee = call.callee;
    if (callee.type === 'Identifier') return callee.name;
    if (callee.type === 'MemberExpression' && !callee.computed && callee.property.type === 'Identifier') {
        return callee.property.name;
    }
    return '';
}

function isConsoleCall(call) {
    return call?.callee?.type === 'MemberExpression'
        && call.callee.object?.type === 'Identifier'
        && call.callee.object.name === 'console';
}

function isExcluded(node, parents) {
    const parent = parents[parents.length - 1];
    // Stable enum values, lookup keys and backend-origin comparisons are data,
    // not user-interface copy. Their localized labels are audited separately.
    if (parent?.type === 'Property' && parent.key === node) return true;
    if (parent?.type === 'MemberExpression' && parent.property === node) return true;
    if (parent?.type === 'SwitchCase' && parent.test === node) return true;
    if (parent?.type === 'BinaryExpression' && ['===', '!==', '==', '!='].includes(parent.operator)) return true;

    const call = [...parents].reverse().find(parent => parent.type === 'CallExpression');
    if (call && isConsoleCall(call)
        && ['log', 'debug', 'info', 'warn', 'error', 'group', 'groupEnd'].includes(calleeName(call))) return true;

    const property = [...parents].reverse().find(parent => parent.type === 'Property');
    if (property && property.key !== node) {
        const name = property.key.type === 'Identifier' ? property.key.name : String(property.key.value || '');
        if (['sql', 'query', 'code', 'raw', 'template'].includes(name.toLowerCase())) return true;
    }
    return false;
}

function isUserVisibleSink(node, parents) {
    const nearestCall = [...parents].reverse().find(parent => parent.type === 'CallExpression');
    if (nearestCall) {
        const name = calleeName(nearestCall);
        const object = nearestCall.callee?.type === 'MemberExpression'
            && nearestCall.callee.object?.type === 'Identifier'
            ? nearestCall.callee.object.name
            : '';
        if (object === 'I18n' && name === 't') return false;
        const argumentIndex = nearestCall.arguments.findIndex(argument => node.start >= argument.start && node.end <= argument.end);
        if (argumentIndex === 0 && ['Toast', 'Utils'].includes(object)
            && ['error', 'success', 'info', 'warning', 'show', 'showToast'].includes(name)) return true;
        if (argumentIndex === 0 && nearestCall.callee?.type === 'Identifier'
            && ['alert', 'confirm', 'prompt'].includes(name)) return true;
    }

    const property = [...parents].reverse().find(parent => parent.type === 'Property' && parent.value === node);
    if (property) {
        const name = property.key.type === 'Identifier' ? property.key.name : String(property.key.value || '');
        if (['textContent', 'placeholder', 'ariaLabel'].includes(name)) return true;
    }

    const assignment = [...parents].reverse().find(parent => parent.type === 'AssignmentExpression' && parent.right === node);
    if (assignment?.left?.type === 'MemberExpression' && !assignment.left.computed) {
        return ['textContent', 'placeholder', 'title', 'ariaLabel'].includes(assignment.left.property.name);
    }
    return false;
}

function literalText(node) {
    if (node.type === 'Literal' && typeof node.value === 'string') return node.value;
    if (node.type === 'TemplateElement') return node.value.cooked || '';
    return '';
}

function isStableTechnicalText(text) {
    return /^(?:https?:\/\/\S+|[a-z0-9._-]+|TOP SQL|Webhook)$/i.test(text);
}

function collectViolations() {
    const counts = new Map();
    const samples = new Map();
    for (const file of walkFiles(sourceRoot)) {
        const source = fs.readFileSync(file, 'utf8');
        const ast = acorn.parse(source, {
            ecmaVersion: 'latest',
            sourceType: 'script',
            locations: true,
            allowHashBang: true,
        });
        walk(ast, (node, parents) => {
            const text = literalText(node).replace(/\s+/g, ' ').trim();
            if (!text || isExcluded(node, parents)) return;
            if (!hanPattern.test(text)
                && !(asciiWordPattern.test(text) && !isStableTechnicalText(text) && isUserVisibleSink(node, parents))) return;
            const relative = path.relative(root, file);
            const key = `${relative}\u0000${text}`;
            counts.set(key, (counts.get(key) || 0) + 1);
            if (!samples.has(key)) samples.set(key, `${relative}:${node.loc.start.line}`);
        });
    }
    return { counts: Object.fromEntries([...counts.entries()].sort()), samples };
}

function main() {
    const { counts, samples } = collectViolations();
    const violations = Object.entries(counts);
    if (violations.length) {
        console.error('Hard-coded user-visible frontend copy detected:');
        for (const [key, count] of violations.slice(0, 50)) {
            console.error(`  ${samples.get(key)} (${count}) ${key.split('\u0000')[1]}`);
        }
        if (violations.length > 50) console.error(`  ... and ${violations.length - 50} more`);
        process.exitCode = 1;
        return;
    }
    console.log('Frontend i18n AST audit passed (0 violations).');
}

main();
