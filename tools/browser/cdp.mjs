/**
 * A Chrome DevTools Protocol client small enough to read in one sitting.
 *
 * The interactive claims in docs/VERTICAL_SLICES.md are about a button: press it and a
 * result appears. Every other test in this repository verifies the request that button
 * sends, which is not the same claim — a handler wired to the wrong element, a control
 * left disabled, or a component that throws on mount would pass all of them and still
 * leave a reader pressing a button that does nothing.
 *
 * So this drives a real browser. Chrome exposes DevTools over a WebSocket, and Node has
 * had a WebSocket client built in since v22, which means the whole thing costs no
 * dependency: no Playwright, no Puppeteer, no browser download. That matters here because
 * the project's rule is that a check should not be harder to run than the thing it checks.
 *
 * Clicks go through Input.dispatchMouseEvent at the element's real coordinates rather than
 * through element.click(). The difference is the point: a synthetic click fires the
 * handler whatever is on top of it, so it would pass on a button covered by an overlay,
 * scrolled off the page, or disabled. Chrome's own hit-testing decides here.
 */
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

/** Where Chrome installs itself on each platform. First hit wins. */
const CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA &&
    join(process.env.LOCALAPPDATA, 'Google/Chrome/Application/chrome.exe'),
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
].filter(Boolean);

export function findChrome() {
  for (const path of CANDIDATES) if (existsSync(path)) return path;
  return null;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * A headless Chrome with the debug port open, and a session attached to one blank tab.
 *
 * The profile is a fresh temporary directory every time. A run that borrowed the user's
 * real profile would inherit their extensions, their cookies and their session, and a
 * check that passes only because someone happened to be logged in is not a check.
 */
export async function launch({ headless = true, windowSize = '1280,1600' } = {}) {
  const binary = findChrome();
  if (!binary) {
    throw new Error(
      'No Chrome or Edge found. Set CHROME_PATH to the executable, or install Chrome.',
    );
  }
  const profile = mkdtempSync(join(tmpdir(), 'aegis-cdp-'));
  const port = await freePort();
  const args = [
    '--remote-debugging-port=' + port,
    '--user-data-dir=' + profile,
    '--window-size=' + windowSize,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--disable-background-networking',
    '--disable-renderer-backgrounding',
    '--hide-scrollbars',
    'about:blank',
  ];
  if (headless) args.unshift('--headless=new', '--disable-gpu');

  const proc = spawn(binary, args, { stdio: 'ignore' });
  const version = await poll(
    () => getJSON('http://127.0.0.1:' + port + '/json/version'),
    20000,
    'Chrome did not open its debug port within 20s (' + binary + ')',
  );

  const browser = await connect(version.webSocketDebuggerUrl);
  const created = await browser.send('Target.createTarget', { url: 'about:blank' });
  const attached = await browser.send('Target.attachToTarget', {
    targetId: created.targetId,
    flatten: true,
  });
  const page = sessionOn(browser, attached.sessionId);

  await page.send('Page.enable');
  await page.send('Runtime.enable');
  await page.send('Network.enable');
  await page.send('Log.enable');

  return {
    binary,
    version: version.Browser,
    page,
    /**
     * Shut the browser down, including the half-dozen processes it spawned.
     *
     * `proc.kill()` alone is not enough on Windows: it signals the process this module
     * started and leaves the renderer, GPU, network and crashpad children running, each
     * still holding the temp profile open. A headful run leaves a visible window behind.
     * `taskkill /T` walks the tree; elsewhere the process group does the same job.
     */
    async close() {
      try {
        browser.socket.close();
      } catch {
        /* already gone */
      }
      if (process.platform === 'win32' && proc.pid) {
        try {
          spawnSync('taskkill', ['/pid', String(proc.pid), '/T', '/F'], {
            stdio: 'ignore',
          });
        } catch {
          /* fall through to the plain kill below */
        }
      }
      proc.kill();
      await sleep(400);
      try {
        rmSync(profile, { recursive: true, force: true });
      } catch {
        /* Windows sometimes still holds the profile open; it is a temp dir either way */
      }
    },
  };
}

/** One WebSocket, request ids matched to promises, events handed to listeners. */
async function connect(url) {
  const socket = new WebSocket(url);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', () => reject(new Error('cannot reach ' + url)), {
      once: true,
    });
  });

  let nextId = 1;
  const pending = new Map();
  const listeners = new Set();

  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const slot = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) slot.reject(new Error(message.error.message));
      else slot.resolve(message.result);
      return;
    }
    for (const listener of listeners) listener(message);
  });

  socket.addEventListener('close', () => {
    for (const slot of pending.values()) {
      slot.reject(new Error('the DevTools connection closed mid-request'));
    }
    pending.clear();
  });

  return {
    socket,
    listeners,
    send(method, params = {}, sessionId) {
      const id = nextId++;
      const payload = { id, method, params };
      if (sessionId) payload.sessionId = sessionId;
      socket.send(JSON.stringify(payload));
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        setTimeout(() => {
          if (pending.has(id)) {
            pending.delete(id);
            reject(new Error(method + ' did not answer within 180s'));
          }
        }, 180000);
      });
    },
  };
}

/** The same connection, scoped to one tab, with event subscription. */
function sessionOn(browser, sessionId) {
  return {
    sessionId,

    send(method, params) {
      return browser.send(method, params, sessionId);
    },

    on(method, handler) {
      const listener = (message) => {
        if (message.sessionId === sessionId && message.method === method) {
          handler(message.params);
        }
      };
      browser.listeners.add(listener);
      return () => browser.listeners.delete(listener);
    },

    /**
     * Evaluate a function body in the page and return its value as JSON.
     *
     * The body runs inside an async IIFE so a check can `await fetch(...)` and assert on
     * what the server actually answered. `awaitPromise` then resolves it before the value
     * comes back, so a synchronous body behaves exactly as before.
     */
    async eval(body) {
      const answer = await this.send('Runtime.evaluate', {
        expression: '(async () => { ' + body + ' })()',
        returnByValue: true,
        awaitPromise: true,
      });
      if (answer.exceptionDetails) {
        const d = answer.exceptionDetails;
        throw new Error('page threw: ' + (d.exception?.description ?? d.text));
      }
      return answer.result.value;
    },

    /** Navigate and wait for the load event, not merely for the navigation to start. */
    async goto(url, timeoutMs = 90000) {
      let done = false;
      const loaded = new Promise((resolve) => {
        const off = this.on('Page.loadEventFired', () => {
          off();
          done = true;
          resolve();
        });
      });
      await this.send('Page.navigate', { url });
      const deadline = Date.now() + timeoutMs;
      while (!done && Date.now() < deadline) await Promise.race([loaded, sleep(100)]);
      if (!done) throw new Error(url + ' did not finish loading in time');
    },

    /** Wait until an expression returns something truthy, or give up loudly. */
    async until(expression, options = {}) {
      const timeoutMs = options.timeoutMs ?? 90000;
      const every = options.every ?? 100;
      const what = options.what ?? expression;
      const deadline = Date.now() + timeoutMs;
      while (Date.now() < deadline) {
        const value = await this.eval('return (' + expression + ');');
        if (value) return value;
        await sleep(every);
      }
      throw new Error('waited ' + timeoutMs / 1000 + 's and never saw: ' + what);
    },

    /**
     * Press an element the way a person does.
     *
     * The coordinates come from the element's own bounding box, and Chrome decides what is
     * actually under them. An element that is hidden, covered, zero-sized or scrolled out
     * of view fails here, which is the entire reason for not calling `.click()`.
     */
    async click(selector) {
      const s = JSON.stringify(selector);
      const box = await this.eval(
        'const el = document.querySelector(' + s + ');' +
          'if (!el) return null;' +
          "el.scrollIntoView({ block: 'center' });" +
          'const r = el.getBoundingClientRect();' +
          'return { x: r.x + r.width / 2, y: r.y + r.height / 2,' +
          '         w: r.width, h: r.height, disabled: !!el.disabled,' +
          '         label: (el.textContent || "").trim() };',
      );
      if (!box) throw new Error('no element matches ' + selector);
      if (box.w === 0 || box.h === 0) throw new Error(selector + ' has no size to click');
      if (box.disabled) throw new Error(selector + ' is disabled');

      const onTop = await this.eval(
        'const el = document.querySelector(' + s + ');' +
          'const r = el.getBoundingClientRect();' +
          'const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);' +
          'return top === el || el.contains(top);',
      );
      if (!onTop) {
        throw new Error(selector + ' is covered by another element at its centre');
      }

      const at = { x: box.x, y: box.y, button: 'left', clickCount: 1 };
      await this.send('Input.dispatchMouseEvent', { type: 'mouseMoved', ...at });
      await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', ...at });
      await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', ...at });
      return box;
    },
  };
}

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(url + ' -> ' + response.status);
  return response.json();
}

async function poll(fn, timeoutMs, message) {
  const deadline = Date.now() + timeoutMs;
  let last;
  while (Date.now() < deadline) {
    try {
      return await fn();
    } catch (error) {
      last = error;
      await sleep(200);
    }
  }
  throw new Error(message + ': ' + (last?.message ?? 'no reason given'));
}

async function freePort() {
  const net = await import('node:net');
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}
