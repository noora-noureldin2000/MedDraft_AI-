import { HumanBrowser } from './human_browser.js';
import { cleanScientificDOM } from './dom_compressor.js';
import { ScholarSurfer } from './scholar_surfer.js';
import { PubMedSurfer } from './pubmed_surfer.js';
import * as path from 'path';
import * as fs from 'fs';
import { fileURLToPath } from 'url';
import { Page } from 'playwright';

// ES Module resolution for __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load env variables
import { config } from 'dotenv';
config({ path: path.resolve(__dirname, '../../../.env') });

function getBrowserConfig() {
  const headless = process.env.BROWSER_HEADLESS !== 'false'; // Default to headless unless specified false
  const proxyServer = process.env.PROXY_SERVER || '';
  const proxyUsername = process.env.PROXY_USERNAME || '';
  const proxyPassword = process.env.PROXY_PASSWORD || '';

  const cfg: any = {
    headless,
    sessionPath: path.resolve(__dirname, '../../auth/academic_state.json')
  };

  // Add proxy if present
  if (proxyServer) {
    cfg.proxy = {
      server: proxyServer,
      ...(proxyUsername && { username: proxyUsername }),
      ...(proxyPassword && { password: proxyPassword })
    };
  }

  // Load custom browser extension path if configured
  if (process.env.CAPTCHASONIC_PATH) {
    cfg.extensionPath = path.resolve(process.env.CAPTCHASONIC_PATH);
  }

  return cfg;
}

const GLOBAL_TIMEOUT_MS = 120_000;

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  if (!command) {
    console.error(JSON.stringify({ error: 'No command specified.' }));
    process.exit(1);
  }

  const browserConfig = getBrowserConfig();
  const browser = new HumanBrowser(browserConfig);
  let page: Page | null = null;

  const timeoutPromise = new Promise<never>((_, reject) => {
    setTimeout(() => reject(new Error(`Global timeout: command "${command}" exceeded ${GLOBAL_TIMEOUT_MS / 1000}s`)), GLOBAL_TIMEOUT_MS);
  });

  try {
    await Promise.race([runCommand(command, args, browser, browserConfig, (p) => { page = p; }), timeoutPromise]);
  } catch (error: any) {
    try {
      if (page) {
        const debugPath = path.resolve(__dirname, '../../../../outputs/browser_error_debug.png');
        const dir = path.dirname(debugPath);
        if (!fs.existsSync(dir)) {
          fs.mkdirSync(dir, { recursive: true });
        }
        await (page as Page).screenshot({ path: debugPath });
        console.error(`Saved error debug screenshot to ${debugPath}`);
      }
    } catch (screenshotError) {
      console.error(`Failed to save debug screenshot: ${screenshotError}`);
    }
    console.error(JSON.stringify({ success: false, error: error.message }));
    process.exit(1);
  } finally {
    await browser.close();
  }
}

async function runCommand(command: string, args: string[], browser: HumanBrowser, browserConfig: any, setPage: (p: Page) => void) {
  const context = await browser.launch();
  const page = await context.newPage();
  setPage(page);

  if (command === 'scholar-search') {
    const query = args[1];
    const limit = args[2] ? parseInt(args[2], 10) : 10;
    if (!query) throw new Error('Missing query argument.');

    const surfer = new ScholarSurfer(browser);
    const results = await surfer.search(page, query, limit);
    console.log(JSON.stringify({ success: true, count: results.length, results }));

  } else if (command === 'pubmed-search') {
    const query = args[1];
    const limit = args[2] ? parseInt(args[2], 10) : 10;
    if (!query) throw new Error('Missing query argument.');

    const surfer = new PubMedSurfer(browser);
    const results = await surfer.search(page, query, limit);
    console.log(JSON.stringify({ success: true, count: results.length, results }));

  } else if (command === 'navigate') {
    const url = args[1];
    if (!url) throw new Error('Missing URL argument.');

    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await browser.delay(2000, 3000);

    await browser.solveReCaptcha(page);

    const tree = await cleanScientificDOM(page);
    console.log(JSON.stringify({ success: true, url: page.url(), tree }));

  } else if (command === 'click') {
    const url = args[1];
    const agentId = args[2];
    if (!url || !agentId) throw new Error('Usage: click <url> <agentId>');

    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await browser.delay(2000, 3000);
    await browser.solveReCaptcha(page);

    await cleanScientificDOM(page);

    const targetElement = page.locator(`[data-agent-id="${agentId}"]`);
    if (await targetElement.count() === 0) {
      throw new Error(`Element with agentId "${agentId}" not found.`);
    }

    console.log(`Clicking element with agent-id ${agentId}...`);
    await targetElement.first().click();
    await page.waitForLoadState('domcontentloaded');
    await browser.delay(2000, 3500);

    const tree = await cleanScientificDOM(page);
    console.log(JSON.stringify({ success: true, url: page.url(), tree }));

  } else if (command === 'download-pdf') {
    const pdfUrl = args[1];
    const outputPath = args[2];
    if (!pdfUrl || !outputPath) throw new Error('Usage: download-pdf <pdfUrl> <outputPath>');

    console.error(`Downloading PDF from ${pdfUrl} to ${outputPath}...`);

    const dir = path.dirname(outputPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    const downloadPromise = page.waitForEvent('download', { timeout: 30000 });

    await page.goto(pdfUrl, { timeout: 30000 }).catch(() => {});

    try {
      const download = await downloadPromise;
      await download.saveAs(outputPath);
      console.log(JSON.stringify({ success: true, path: outputPath }));
    } catch (e: any) {
      const response = await page.request.get(pdfUrl);
      if (response.ok()) {
        const buffer = await response.body();
        fs.writeFileSync(outputPath, buffer);
        console.log(JSON.stringify({ success: true, path: outputPath }));
      } else {
        throw new Error(`Failed to download PDF. Status: ${response.status()}`);
      }
    }

  } else {
    throw new Error(`Unknown command: ${command}`);
  }
}

main();
