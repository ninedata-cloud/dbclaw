#!/usr/bin/env node
/* Extract visible Chinese fragments from first-party JS string literals. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
global.window = global;
for (const relative of [
    'frontend/js/locales/zh-CN.js',
    'frontend/js/locales/en-US.js',
    'frontend/js/locales/generated-ui.js',
]) {
    vm.runInThisContext(fs.readFileSync(path.join(root, relative), 'utf8'), { filename: relative });
}

function collectFiles(input, output = []) {
    const stat = fs.statSync(input);
    if (stat.isDirectory()) {
        for (const name of fs.readdirSync(input)) {
            if (name === 'locales') continue;
            collectFiles(path.join(input, name), output);
        }
    } else if (input.endsWith('.js')) {
        output.push(input);
    }
    return output;
}

function extractPhrases(files) {
    const existing = DBClawLocales['en-US'].legacy;
    const phrases = new Set();
    const stringPattern = /(?:'([^'\\]*(?:\\.[^'\\]*)*)'|"([^"\\]*(?:\\.[^"\\]*)*)"|`([^`\\]*(?:\\.[^`\\]*)*)`)/gs;
    const phrasePattern = /[\u3400-\u9fff][\u3400-\u9fffA-Za-z0-9\s，。！？：；、、“”‘’（）()\/+.#\[\]_-]*/g;

    for (const file of files) {
        const source = fs.readFileSync(file, 'utf8');
        let match;
        while ((match = stringPattern.exec(source))) {
            const literal = match[1] ?? match[2] ?? match[3] ?? '';
            const parts = literal.split(/<[^>]*>|\$\{[^}]*\}|\\[nrt]|\n/g);
            for (const part of parts) {
                for (let phrase of part.match(phrasePattern) || []) {
                    phrase = phrase
                        .replace(/\\[nrt]/g, ' ')
                        .replace(/\s+/g, ' ')
                        .trim();
                    if (phrase && /[\u3400-\u9fff]/.test(phrase) && !existing[phrase]) phrases.add(phrase);
                }
            }
        }
    }
    return [...phrases].sort((left, right) => left.localeCompare(right, 'zh-CN'));
}

function normalizeTranslation(value) {
    return value
        .replace(/data source/gi, match => match[0] === 'D' ? 'Datasource' : 'datasource')
        .replace(/large language model/gi, 'AI model')
        .replace(/intelligent inspection/gi, 'smart inspection')
        .replace(/\s+([,.;:!?])/g, '$1')
        .trim();
}

async function translateBatch(phrases) {
    const translations = {};
    for (let offset = 0; offset < phrases.length; offset += 24) {
        const batch = phrases.slice(offset, offset + 24);
        const marker = `[[[DBCLAW_SPLIT_${offset}]]]`;
        const query = batch.join(`\n${marker}\n`);
        const url = new URL('https://translate.googleapis.com/translate_a/single');
        url.search = new URLSearchParams({ client: 'gtx', sl: 'zh-CN', tl: 'en-US', dt: 't', q: query });
        const response = await fetch(url);
        if (!response.ok) throw new Error(`Translation request failed: ${response.status}`);
        const payload = await response.json();
        const translated = payload[0].map(item => item[0]).join('');
        const values = translated.split(new RegExp(`\\s*${marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*`));
        if (values.length !== batch.length) throw new Error(`Translation batch mismatch at ${offset}`);
        batch.forEach((phrase, index) => { translations[phrase] = normalizeTranslation(values[index]); });
    }
    return translations;
}

async function main() {
    const shouldTranslate = process.argv.includes('--translate');
    const requested = process.argv.slice(2).filter(value => value !== '--translate');
    const inputs = requested.length ? requested : ['frontend/js'];
    const files = inputs.flatMap(value => collectFiles(path.resolve(root, value)));
    const phrases = extractPhrases(files);
    const result = shouldTranslate ? await translateBatch(phrases) : phrases;
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
