import { jitterDelay } from './util.js';
function elementKey(e) {
    return `${e.tag}|${e.text}|${e.href ?? ''}|${e.attrs['type'] ?? ''}`;
}
/**
 * Renders a snapshot as compact text for LLM consumption.
 * `[i]` addresses elements for click/type; `*` marks elements new since the previous snapshot.
 */
function serializeSnapshot(s) {
    const lines = [
        `[${s.title}](${s.url})`,
        `Viewport ${s.viewport.width}x${s.viewport.height} · ${s.scroll.abovePx}px above · ${s.scroll.belowPx}px below`,
        '',
    ];
    for (const e of s.elements) {
        const parts = [`[${e.index}]${e.isNew ? '*' : ''} <${e.tag}>`];
        if (e.text)
            parts.push(`"${e.text}"`);
        for (const [k, v] of Object.entries(e.attrs))
            parts.push(`${k}=${v}`);
        if (e.href)
            parts.push(`» ${e.href}`);
        lines.push(parts.join(' '));
    }
    return lines.join('\n');
}
export class PageController {
    page = null;
    previousKeys = new Set();
    attach(page) {
        this.page = page;
        this.previousKeys.clear();
    }
    boundTo() {
        return this.page;
    }
    pageRef() {
        if (!this.page)
            throw new Error('No page attached to controller.');
        return this.page;
    }
    /**
     * Extracts interactive elements and stamps data-agent-index attributes in one pass.
     * The function body is fully self-contained: Playwright serializes its source and
     * runs it inside the page, where closures over Node-scope constants do not exist.
     */
    async snapshot() {
        const page = this.pageRef();
        const raw = await page.evaluate(() => {
            const INTERACTIVE_TAGS = new Set(['a', 'button', 'input', 'select', 'textarea', 'summary']);
            const INTERACTIVE_ROLES = new Set([
                'button', 'link', 'checkbox', 'radio', 'tab', 'menuitem', 'option',
                'textbox', 'searchbox', 'combobox', 'switch', 'slider',
            ]);
            const ATTR_WHITELIST = ['type', 'placeholder', 'aria-label', 'title', 'name', 'value', 'checked'];
            document.querySelectorAll('[data-agent-index]').forEach((el) => el.removeAttribute('data-agent-index'));
            const out = [];
            const indexed = new WeakSet();
            const hasIndexedAncestor = (el) => {
                let cur = el.parentElement;
                while (cur) {
                    if (indexed.has(cur))
                        return true;
                    cur = cur.parentElement;
                }
                return false;
            };
            for (const el of Array.from(document.querySelectorAll('*'))) {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || el.getAttribute('aria-hidden') === 'true')
                    continue;
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 && rect.height <= 0)
                    continue;
                const tagLower = el.tagName.toLowerCase();
                const role = el.getAttribute('role') || '';
                const isCoreTag = INTERACTIVE_TAGS.has(tagLower);
                const hasClickHandler = el.hasAttribute('onclick') || el.getAttribute('contenteditable') === 'true';
                const cursorPointer = style.cursor === 'pointer';
                const interactive = isCoreTag ||
                    INTERACTIVE_ROLES.has(role) ||
                    hasClickHandler ||
                    (cursorPointer && (el.textContent?.trim().length ?? 0) > 0);
                if (!interactive)
                    continue;
                // Generic pointer-styled wrappers under an indexed control add no addressable target
                if (!isCoreTag && !INTERACTIVE_ROLES.has(role) && hasIndexedAncestor(el))
                    continue;
                const index = out.length;
                el.setAttribute('data-agent-index', String(index));
                indexed.add(el);
                const attrs = {};
                if (role)
                    attrs.role = role;
                for (const name of ATTR_WHITELIST) {
                    const val = el.getAttribute(name);
                    if (val)
                        attrs[name] = val.replace(/\s+/g, ' ').slice(0, 100);
                }
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200);
                out.push({
                    index,
                    tag: tagLower,
                    text,
                    href: tagLower === 'a' ? el.href || null : null,
                    attrs,
                });
            }
            return out;
        });
        const keys = new Set(raw.map(elementKey));
        const firstSnapshot = this.previousKeys.size === 0;
        const elements = raw.map((e) => ({
            ...e,
            isNew: !firstSnapshot && !this.previousKeys.has(elementKey(e)),
        }));
        this.previousKeys = keys;
        const scroll = await page.evaluate(() => ({
            abovePx: Math.max(0, Math.round(window.scrollY)),
            belowPx: Math.max(0, Math.round((document.documentElement.scrollHeight || 0) - window.innerHeight - window.scrollY)),
        }));
        const viewport = page.viewportSize() ?? { width: 0, height: 0 };
        const partial = {
            url: page.url(),
            title: await page.title(),
            viewport,
            scroll,
            elements,
            serialized: '',
        };
        partial.serialized = serializeSnapshot(partial);
        return partial;
    }
    async click(index) {
        const page = this.pageRef();
        const locator = page.locator(`[data-agent-index="${index}"]`);
        if ((await locator.count()) === 0) {
            throw new Error(`No element for index ${index} — the page changed since the last snapshot. Call state.`);
        }
        const clicked = (await locator.first().textContent())?.replace(/\s+/g, ' ').trim().slice(0, 80) ?? '';
        const pagesBefore = page.context().pages().length;
        await locator.first().click({ timeout: 8000 });
        await page.waitForLoadState('domcontentloaded', { timeout: 15000 }).catch(() => { });
        const pagesAfter = page.context().pages();
        return {
            clicked,
            newTabIndex: pagesAfter.length > pagesBefore ? pagesAfter.length - 1 : null,
        };
    }
    async type(index, text, submit) {
        const page = this.pageRef();
        const locator = page.locator(`[data-agent-index="${index}"]`);
        if ((await locator.count()) === 0) {
            throw new Error(`No element for index ${index} — the page changed since the last snapshot. Call state.`);
        }
        await locator.first().click({ timeout: 8000 });
        for (const char of text) {
            await page.keyboard.type(char);
            await jitterDelay(50, 180);
        }
        if (submit) {
            await page.keyboard.press('Enter');
            await page.waitForLoadState('domcontentloaded', { timeout: 15000 }).catch(() => { });
        }
    }
    async scroll(down, pixels) {
        const page = this.pageRef();
        await page.mouse.wheel(0, down ? pixels : -pixels);
    }
    async settle(minMs = 1200, maxMs = 2800) {
        await jitterDelay(minMs, maxMs);
    }
}
