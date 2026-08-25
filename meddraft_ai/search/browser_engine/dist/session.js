import * as fs from 'fs';
import * as path from 'path';
import * as readline from 'readline';
import { HumanBrowser } from './human_browser.js';
import { PageController } from './page_controller.js';
import { withTimeout } from './util.js';
const OP_TIMEOUT_MS = 90_000;
function requireString(args, key) {
    const val = args[key];
    if (typeof val !== 'string' || val.trim() === '') {
        throw new Error(`Missing or invalid argument "${key}" (expected non-empty string).`);
    }
    return val.trim();
}
function optionalIndex(args, key, fallback) {
    const val = args[key];
    if (val === undefined || val === null)
        return fallback;
    if (typeof val !== 'number' || !Number.isInteger(val) || val < 0) {
        throw new Error(`Invalid argument "${key}" (expected non-negative integer).`);
    }
    return val;
}
export async function runSession(config) {
    // Protocol purity: stdin/stdout carry JSONL only; library chatter is routed to stderr.
    console.log = (...args) => {
        console.error(...args);
    };
    const respond = (payload) => {
        process.stdout.write(JSON.stringify(payload) + '\n');
    };
    const human = new HumanBrowser(config);
    const controller = new PageController();
    let context = null;
    let activePageIndex = 0;
    async function ensureContext() {
        if (!context)
            context = await human.launch();
        return context;
    }
    async function bindActivePage() {
        const ctx = await ensureContext();
        let pages = ctx.pages();
        if (pages.length === 0) {
            pages = [await ctx.newPage()];
            activePageIndex = 0;
        }
        activePageIndex = Math.min(activePageIndex, pages.length - 1);
        const page = pages[activePageIndex];
        if (controller.boundTo() !== page)
            controller.attach(page);
        return page;
    }
    async function snapshotOrThrow() {
        await bindActivePage();
        return controller.snapshot();
    }
    const handlers = {
        goto: async (args) => {
            const url = requireString(args, 'url');
            let parsed;
            try {
                parsed = new URL(url);
            }
            catch {
                throw new Error(`Invalid URL: ${url}`);
            }
            if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
                throw new Error(`Unsupported protocol: ${parsed.protocol}`);
            }
            const page = await bindActivePage();
            await withTimeout(page.goto(parsed.href, { waitUntil: 'domcontentloaded', timeout: 30000 }), OP_TIMEOUT_MS, `goto ${parsed.href}`);
            await human.solveReCaptcha(page);
            await controller.settle();
            return { snapshot: await controller.snapshot() };
        },
        state: async () => ({ snapshot: await snapshotOrThrow() }),
        click: async (args) => {
            await bindActivePage();
            const index = optionalIndex(args, 'index', -1);
            if (index < 0)
                throw new Error('Missing or invalid argument "index" (expected non-negative integer).');
            const result = await controller.click(index);
            await controller.settle();
            return {
                clicked: result.clicked,
                newTabIndex: result.newTabIndex,
                hint: result.newTabIndex !== null ? `Link opened in a new tab (index ${result.newTabIndex}) — use select_tab.` : undefined,
                snapshot: await controller.snapshot(),
            };
        },
        type: async (args) => {
            await bindActivePage();
            const index = optionalIndex(args, 'index', -1);
            if (index < 0)
                throw new Error('Missing or invalid argument "index" (expected non-negative integer).');
            const text = requireString(args, 'text');
            if (text.length > 500)
                throw new Error('Argument "text" exceeds 500 characters.');
            const submit = args['submit'] === true;
            await controller.type(index, text, submit);
            await controller.settle(1000, 2200);
            return { typedLength: text.length, submitted: submit, snapshot: await controller.snapshot() };
        },
        scroll: async (args) => {
            await bindActivePage();
            const down = args['down'] !== false;
            const pixels = Math.min(5000, Math.max(100, optionalIndex(args, 'pixels', 600)));
            await controller.scroll(down, pixels);
            await controller.settle(500, 1000);
            return { scrolled: down ? pixels : -pixels, snapshot: await controller.snapshot() };
        },
        tabs: async () => {
            const ctx = await ensureContext();
            const tabs = await Promise.all(ctx.pages().map(async (page, index) => ({
                index,
                url: page.url(),
                title: await page.title().catch(() => ''),
            })));
            return { tabs, activeIndex: activePageIndex };
        },
        select_tab: async (args) => {
            const ctx = await ensureContext();
            const index = optionalIndex(args, 'index', -1);
            if (index < 0 || index >= ctx.pages().length) {
                throw new Error(`Tab index ${index} out of range (0..${ctx.pages().length - 1}).`);
            }
            activePageIndex = index;
            const page = ctx.pages()[index];
            controller.attach(page);
            await page.bringToFront().catch(() => { });
            return { activeIndex: index, snapshot: await controller.snapshot() };
        },
        download: async (args) => {
            const url = requireString(args, 'url');
            const outputPath = requireString(args, 'path');
            const ctx = await ensureContext();
            const response = await withTimeout(ctx.request.get(url), OP_TIMEOUT_MS, `download ${url}`);
            if (!response.ok()) {
                throw new Error(`Download failed with status ${response.status()} for ${url}`);
            }
            const body = await response.body();
            fs.mkdirSync(path.dirname(outputPath), { recursive: true });
            fs.writeFileSync(outputPath, body);
            return { path: outputPath, bytes: body.length, status: response.status() };
        },
        captcha: async () => {
            const page = await bindActivePage();
            return { solved: await human.solveReCaptcha(page) };
        },
    };
    const rl = readline.createInterface({ input: process.stdin, terminal: false });
    for await (const line of rl) {
        const trimmed = line.trim();
        if (!trimmed)
            continue;
        let request;
        try {
            request = JSON.parse(trimmed);
        }
        catch {
            respond({ id: null, ok: false, error: `Malformed JSON line: ${trimmed.slice(0, 120)}` });
            continue;
        }
        const id = request.id ?? null;
        if (request.op === 'close') {
            respond({ id, ok: true, bye: true });
            rl.close();
            break;
        }
        try {
            const op = typeof request.op === 'string' ? request.op : '';
            const handler = handlers[op];
            if (!handler) {
                throw new Error(`Unknown op "${op}". Available: ${Object.keys(handlers).join(', ')}, close.`);
            }
            const result = await handler(request);
            const payload = { id, ok: true };
            for (const [key, value] of Object.entries(result)) {
                if (value !== undefined)
                    payload[key] = value;
            }
            respond(payload);
        }
        catch (error) {
            respond({ id, ok: false, error: error instanceof Error ? error.message : String(error) });
        }
    }
    try {
        await human.close();
    }
    finally {
        // A finished session must not linger on internal handles
        process.exit(0);
    }
}
