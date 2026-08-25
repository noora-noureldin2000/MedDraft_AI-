import { chromium } from 'playwright-extra';
import stealthPlugin from 'puppeteer-extra-plugin-stealth';
import * as path from 'path';
import * as fs from 'fs';
import { Browser, BrowserContext, Page } from 'playwright';

// The stealth UA override ships a stale hardcoded agent that fights the browser's
// own consistent identity; the native Chromium UA + client hints are already coherent.
const stealth = stealthPlugin();
stealth.enabledEvasions.delete('user-agent-override');
chromium.use(stealth);

export interface BrowserConfig {
  headless: boolean;
  proxy?: {
    server: string;
    username?: string;
    password?: string;
  };
  extensionPath?: string; // Path to CaptchaSonic or other unpacked extensions
  sessionPath?: string;    // Storage state JSON path
  locale?: string;         // e.g. "en-US" — set only when aligning with a proxy
  timezoneId?: string;     // e.g. "America/New_York" — set only when aligning with a proxy
}

export class HumanBrowser {
  private config: BrowserConfig;
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;
  private userDataDir: string | null = null;

  constructor(config: BrowserConfig) {
    this.config = config;
    // Set a persistent user data directory if using extensions or maintaining state
    if (this.config.extensionPath || this.config.sessionPath) {
      const baseDir = path.dirname(this.config.sessionPath || './auth/academic_state.json');
      this.userDataDir = path.join(baseDir, 'chrome_user_data');
      if (!fs.existsSync(this.userDataDir)) {
        fs.mkdirSync(this.userDataDir, { recursive: true });
      }
    }
  }

  async launch(): Promise<BrowserContext> {
    const launchArgs: string[] = [
      '--disable-blink-features=AutomationControlled',
    ];

    if (this.config.extensionPath) {
      const extAbsPath = path.resolve(this.config.extensionPath);
      launchArgs.push(
        `--disable-extensions-except=${extAbsPath}`,
        `--load-extension=${extAbsPath}`
      );
    }

    // Headful: viewport null keeps inner/outer window metrics consistent (a real
    // browser trait). Headless: a randomized compact viewport.
    const contextOptions: any = {};
    if (this.config.locale) contextOptions.locale = this.config.locale;
    if (this.config.timezoneId) contextOptions.timezoneId = this.config.timezoneId;
    if (!this.config.headless) {
      contextOptions.viewport = null;
    } else {
      const viewportWidth = Math.floor(Math.random() * (1440 - 1024 + 1)) + 1024;
      const viewportHeight = Math.floor(Math.random() * (900 - 640 + 1)) + 640;
      contextOptions.viewport = { width: viewportWidth, height: viewportHeight };
    }

    if (this.config.proxy) {
      contextOptions.proxy = this.config.proxy;
    }

    if (this.userDataDir) {
      // Extensions and persistent contexts require launchPersistentContext
      this.context = await chromium.launchPersistentContext(this.userDataDir, {
        headless: this.config.headless,
        args: launchArgs,
        ...contextOptions
      });
    } else {
      this.browser = await chromium.launch({
        headless: this.config.headless,
        args: launchArgs,
      });
      // Load session state if exists
      if (this.config.sessionPath && fs.existsSync(this.config.sessionPath)) {
        contextOptions.storageState = this.config.sessionPath;
      }
      this.context = await this.browser.newContext(contextOptions);
    }

    return this.context;
  }

  async close(): Promise<void> {
    // Save storage state before closing if path is configured
    if (this.context && this.config.sessionPath && !this.userDataDir) {
      const dir = path.dirname(this.config.sessionPath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      await this.context.storageState({ path: this.config.sessionPath });
    }

    if (this.context) {
      await this.context.close();
    }
    if (this.browser) {
      await this.browser.close();
    }
  }

  /**
   * Enforces realistic typing delays per character.
   */
  async typeHumanLike(page: Page, selector: string, text: string): Promise<void> {
    const element = page.locator(selector);
    await element.click();
    await page.waitForTimeout(Math.floor(Math.random() * 300) + 200);

    for (const char of text) {
      await page.keyboard.type(char);
      const delay = Math.floor(Math.random() * 150) + 50; // 50-200ms delay per key
      await page.waitForTimeout(delay);
    }
  }

  /**
   * Enforces random pauses between browser interactions.
   */
  async delay(minMs = 1500, maxMs = 4000): Promise<void> {
    const delayTime = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
    await new Promise((resolve) => setTimeout(resolve, delayTime));
  }

  /**
   * Attempts the reCAPTCHA checkbox. Instant passes return true; interactive
   * challenges must be solved manually in the headful window.
   */
  async solveReCaptcha(page: Page): Promise<boolean> {
    try {
      console.log('🔄 Checking for reCAPTCHA on page...');

      // Look for the reCAPTCHA anchor iframe
      const anchorFrames = page.frames().filter(f => f.url().includes('recaptcha/api2/anchor'));
      if (anchorFrames.length === 0) {
        console.log('ℹ️ No reCAPTCHA anchor found.');
        return false;
      }

      const anchorFrame = anchorFrames[0];
      const checkbox = await anchorFrame.waitForSelector('#recaptcha-anchor', { timeout: 5000 });
      if (!checkbox) return false;

      // Click the checkbox and hope for an instant pass
      console.log('👆 Clicking reCAPTCHA checkbox...');
      await checkbox.click();
      await this.delay(1000, 2000);

      const isChecked = await checkbox.getAttribute('aria-checked');
      if (isChecked === 'true') {
        console.log('✅ reCAPTCHA solved.');
        return true;
      }

      console.log('❌ Interactive CAPTCHA challenge presented — solve it manually in the browser window (headful mode), then re-run the command.');
      return false;
    } catch (e) {
      console.error('⚠️ Error in solveReCaptcha:', e);
      return false;
    }
  }
}
