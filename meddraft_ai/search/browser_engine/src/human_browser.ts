import { chromium } from 'playwright-extra';
import stealthPlugin from 'puppeteer-extra-plugin-stealth';
import * as path from 'path';
import * as fs from 'fs';
import { Browser, BrowserContext, Page, ElementHandle } from 'playwright';
import { spawn } from 'child_process';

chromium.use(stealthPlugin());

export interface BrowserConfig {
  headless: boolean;
  proxy?: {
    server: string;
    username?: string;
    password?: string;
  };
  extensionPath?: string; // Path to CaptchaSonic or other unpacked extensions
  sessionPath?: string;    // Storage state JSON path
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

    const viewportWidth = Math.floor(Math.random() * (1920 - 1280 + 1)) + 1280;
    const viewportHeight = Math.floor(Math.random() * (1080 - 720 + 1)) + 720;

    const contextOptions: any = {
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      viewport: { width: viewportWidth, height: viewportHeight },
      locale: 'en-US',
      timezoneId: 'America/New_York',
      geolocation: { longitude: -73.935242, latitude: 40.730610 },
      permissions: ['geolocation'],
    };

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
   * Attempts to solve reCAPTCHA using speech-to-text (GoogleRecaptchaBypass model)
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

      // Click the checkbox
      console.log('👆 Clicking reCAPTCHA checkbox...');
      await checkbox.click();
      await this.delay(1000, 2000);

      // Check if solved immediately
      const isChecked = await checkbox.getAttribute('aria-checked');
      if (isChecked === 'true') {
        console.log('✅ reCAPTCHA solved immediately without challenge.');
        return true;
      }

      // Check if challenge frame is visible
      const bframes = page.frames().filter(f => f.url().includes('recaptcha/api2/bframe'));
      if (bframes.length === 0) {
        console.log('ℹ️ No challenge frame found.');
        return false;
      }

      const bframe = bframes[0];
      console.log('🎧 Switching to audio challenge...');
      
      const audioButton = await bframe.waitForSelector('#recaptcha-audio-button', { timeout: 5000 });
      if (!audioButton) {
        console.log('❌ Audio button not found in challenge frame.');
        return false;
      }
      await audioButton.click();
      await this.delay(2000, 3000);

      // Check if Google blocked us from audio challenge
      const isBlocked = await bframe.$('.rc-dsa-audio-blocked, .rc-audiochallenge-error-message');
      if (isBlocked) {
        console.log('❌ Google blocked audio challenge (too many attempts or suspicious activity).');
        return false;
      }

      // Get audio URL
      const downloadLink = await bframe.waitForSelector('.rc-audiochallenge-download-link', { timeout: 5000 });
      if (!downloadLink) {
        console.log('❌ Audio download link not found.');
        return false;
      }
      const audioUrl = await downloadLink.getAttribute('href');
      if (!audioUrl) return false;

      console.log(`🎵 Audio URL found: ${audioUrl}`);

      // Call Python backend to solve speech to text
      const transcript = await this.transcribeAudio(audioUrl);
      if (!transcript) {
        console.log('❌ Audio transcription failed.');
        return false;
      }

      console.log(`📝 Transcribed text: "${transcript}"`);

      // Input transcript into challenge text box
      const inputField = await bframe.waitForSelector('#audio-response', { timeout: 5000 });
      if (!inputField) return false;
      await inputField.fill(transcript);
      await this.delay(1000, 2000);

      // Click verify button
      const verifyButton = await bframe.waitForSelector('#recaptcha-verify-button', { timeout: 5000 });
      if (!verifyButton) return false;
      await verifyButton.click();
      await this.delay(2000, 3000);

      // Check if solved
      const isSolved = await checkbox.getAttribute('aria-checked');
      if (isSolved === 'true') {
        console.log('✅ reCAPTCHA solved successfully via audio transcription!');
        return true;
      } else {
        console.log('❌ reCAPTCHA solve verification failed.');
        return false;
      }
    } catch (e) {
      console.error('⚠️ Error in solveReCaptcha:', e);
      return false;
    }
  }

  /**
   * Transcribes audio using Python's speech recognition / Google STT API.
   * Calls a helper script `agent_core/web_scraper/transcribe.py` via subprocess.
   */
  private async transcribeAudio(audioUrl: string): Promise<string | null> {
    return new Promise((resolve) => {
      // Find the transcription helper script relative to workspace
      const transcribeScript = path.resolve(__dirname, '../../web_scraper/transcribe.py');
      
      console.log(`Calling Python transcriber: ${transcribeScript}`);
      
      const py = spawn('python', [transcribeScript, audioUrl]);
      let stdout = '';
      let stderr = '';

      py.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      py.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      py.on('close', (code) => {
        if (code === 0) {
          resolve(stdout.trim());
        } else {
          console.error(`Transcription script failed with code ${code}. Error: ${stderr}`);
          resolve(null);
        }
      });
    });
  }
}
