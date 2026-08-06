import { Page } from 'playwright';

export interface CompressedNode {
  agentId: number;
  tagName: string;
  text: string;
  role: string;
  href: string | null;
  className: string;
}

/**
 * Extracts and minifies the DOM for scientific research sites, targeting only high-value interactive nodes.
 */
export async function cleanScientificDOM(page: Page): Promise<CompressedNode[]> {
  const accessibleTree = await page.evaluate(() => {
    // Select input fields, buttons, links, and search result headings/containers for Scholar and PubMed
    const selector = 'input, button, a, h3, .gs_rt, .docsum-title, .gs_rs, .docsum-snippet';
    const elements = document.querySelectorAll(selector);
    
    let agentIdCounter = 0;
    const nodes: CompressedNode[] = [];

    elements.forEach((el) => {
      // Basic visibility check
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') {
        return;
      }

      // Check if it's inside an ignored block (nav/header/footer) to reduce noise
      let currentParent = el.parentElement;
      let shouldIgnore = false;
      while (currentParent) {
        const tagName = currentParent.tagName.toLowerCase();
        if (tagName === 'footer' || tagName === 'header' || tagName === 'nav') {
          shouldIgnore = true;
          break;
        }
        currentParent = currentParent.parentElement;
      }
      if (shouldIgnore) return;

      const text = el.textContent?.trim() || '';
      const role = el.getAttribute('role') || '';
      const href = (el as HTMLAnchorElement).href || null;
      const className = el.className || '';

      // Skip elements that have absolutely no text and aren't input fields or buttons
      const isInputOrButton = el.tagName === 'INPUT' || el.tagName === 'BUTTON';
      if (!text && !isInputOrButton && !href) {
        return;
      }

      // Assign tracking ID to live DOM
      const agentId = agentIdCounter++;
      el.setAttribute('data-agent-id', agentId.toString());

      nodes.push({
        agentId,
        tagName: el.tagName,
        text: text.slice(0, 300), // Cap length per element to save tokens
        role,
        href,
        className
      });
    });

    return nodes;
  });

  // Return a minified JSON representation filtering out items with no content/action
  return accessibleTree.filter(
    (item) => item.text.length > 0 || item.tagName === 'INPUT' || item.tagName === 'BUTTON'
  );
}
