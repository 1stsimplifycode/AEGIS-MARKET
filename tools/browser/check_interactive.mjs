/**
 * Press the buttons.
 *
 * `tests/integration/test_backend_e2e.py` proves the request behind the button: the right
 * path, the right contract, a real computation at the end of it. What it cannot prove is
 * that a person clicking the button causes that request, because it never renders the
 * page. Those are different claims, and the gap between them is where the ordinary
 * frontend failures live — a handler attached to the wrong element, a control that stays
 * disabled, a component that throws during hydration, a result that arrives and is never
 * drawn.
 *
 * So this starts the real backend, starts the real interface, opens a real Chrome, and
 * clicks. Nothing is stubbed. The numbers that appear on screen are then matched against
 * the bytes of the HTTP response the browser actually received, which is the only way to
 * show that what a reader sees came from the analysis rather than from the page.
 *
 * Run it:  node tools/browser/check_interactive.mjs
 *          node tools/browser/check_interactive.mjs --headful     watch it happen
 *          node tools/browser/check_interactive.mjs --url http://localhost:3000
 */
import { spawn } from 'node:child_process';
import { existsSync, openSync, readFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { launch, sleep } from './cdp.mjs';

const REPO = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const argv = process.argv.slice(2);
const flag = (name) => argv.includes('--' + name);
const option = (name) => {
  const i = argv.indexOf('--' + name);
  return i >= 0 ? argv[i + 1] : null;
};

const checks = [];
let failures = 0;

/**
 * The transactional vocabulary this product may never use.
 *
 * A subset of the list `tests/unit/test_non_advisory.py` owns — enough to catch a page
 * that has started giving advice, without duplicating a policy that has a home.
 */
const ADVISORY = [
  /\bbuy\b(?!back)/i, /\bsell\b/i, /\btarget price\b/i, /\bprice target\b/i,
  /\bbest stock\b/i, /\brecommend(?:ation|ed|s)?\b/i, /\bportfolio allocation\b/i,
  /\bshould (?:buy|sell|hold)\b/i, /\bfair value\b/i, /\bstop loss\b/i,
];

/**
 * Remove the standing notice before scanning.
 *
 * It says those words in order to disclaim them, which is the one place they belong. Cut
 * the sentence rather than loosening the patterns, so they still catch the words anywhere
 * else on the page.
 */
function scrubDisclaimer(text) {
  return text
    .replace(/does not provide financial advice[^.]*\./gi, '')
    .replace(/not a basis for any transaction[^.]*\./gi, '');
}


/** One named claim, its verdict, and — when it fails — what was seen instead. */
function check(name, ok, detail = '') {
  checks.push({ name, ok, detail });
  const mark = ok ? '  ok  ' : ' FAIL ';
  process.stdout.write(mark + name + (detail ? '\n         ' + detail : '') + '\n');
  if (!ok) failures += 1;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function waitFor(url, timeoutMs, what) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      /* not up yet */
    }
    await sleep(400);
  }
  throw new Error(what + ' never answered at ' + url);
}

/**
 * The backend and the interface, wired to each other on ephemeral ports.
 *
 * Their output goes to files rather than to pipes: this process does not read them while
 * they run, and an undrained pipe fills at about sixty kilobytes and then blocks the
 * writer for good — the same trap the Python end-to-end suite hit and documents.
 */
async function startStack(activeWeek) {
  const python = existsSync(join(REPO, '.venv/Scripts/python.exe'))
    ? join(REPO, '.venv/Scripts/python.exe')
    : 'python';
  const backendPort = await freePort();
  const webPort = await freePort();
  const logs = join(REPO, '.next-check');
  const out = (name) => {
    const path = join(logs, name);
    return { path, fd: openSync(path, 'w') };
  };
  await import('node:fs').then((fs) => fs.mkdirSync(logs, { recursive: true }));

  const backendLog = out('backend.log');
  // The active week has to reach the backend too.
  //
  // It did not, and that mattered: the backend inherited no `AEGIS_ACTIVE_WEEK`, defaulted
  // to the complete system, and every "the API is gated" check here was really testing the
  // proxy in front of it. A launcher starts both processes at the same week, so the check
  // has to as well — otherwise it verifies a configuration nobody runs.
  const backend = spawn(python, ['-m', 'backend.server', '--port', String(backendPort)], {
    cwd: REPO,
    stdio: ['ignore', backendLog.fd, backendLog.fd],
    env: {
      ...process.env,
      AEGIS_ACTIVE_WEEK: String(activeWeek ?? process.env.AEGIS_ACTIVE_WEEK ?? 1),
    },
  });

  const webLog = out('web.log');
  const web = spawn(
    process.execPath,
    [join(REPO, 'node_modules/next/dist/bin/next'), 'dev', '-p', String(webPort)],
    {
      cwd: REPO,
      stdio: ['ignore', webLog.fd, webLog.fd],
      env: {
        ...process.env,
        AEGIS_BACKEND_URL: 'http://127.0.0.1:' + backendPort,
        NEXT_TELEMETRY_DISABLED: '1',
        // Its own build directory. Sharing `.next` with the developer's dev server or
        // with the output of `next build` interleaves two builds, and what comes out is
        // a webpack module error or a 404 that looks like an application bug.
        AEGIS_DIST_DIR: '.next-check/next',
        // Run this the way a mentor demonstration runs: week 1 enabled, the rest
        // built and gated. The feature and the gate are then verified against one
        // process rather than two configurations that could drift apart.
        AEGIS_ACTIVE_WEEK: String(
          activeWeek ?? process.env.AEGIS_ACTIVE_WEEK ?? 1,
        ),
      },
    },
  );

  const stop = () => {
    for (const proc of [backend, web]) {
      try {
        if (process.platform === 'win32') {
          spawn('taskkill', ['/pid', String(proc.pid), '/T', '/F'], { stdio: 'ignore' });
        } else {
          proc.kill('SIGTERM');
        }
      } catch {
        /* already gone */
      }
    }
  };

  try {
    await waitFor(
      'http://127.0.0.1:' + backendPort + '/api/health',
      120000,
      'the analysis backend',
    );
    await waitFor('http://127.0.0.1:' + webPort, 180000, 'the interface');
  } catch (error) {
    stop();
    const tail = (p) => {
      try {
        return readFileSync(p, 'utf-8').slice(-1500);
      } catch {
        return '(no log)';
      }
    };
    throw new Error(
      error.message + '\n--- backend ---\n' + tail(backendLog.path) +
        '\n--- web ---\n' + tail(webLog.path),
    );
  }

  return { url: 'http://127.0.0.1:' + webPort, backendPort, stop };
}

/** Console errors and uncaught exceptions, collected for the whole session. */
function watchForErrors(page) {
  const problems = [];
  page.on('Runtime.exceptionThrown', (p) => {
    const details = p.exceptionDetails ?? {};
    const where = (details.stackTrace?.callFrames ?? [])
      .slice(0, 4)
      .map((f) => (f.functionName || '(anonymous)') + ' @ ' + f.url + ':' + (f.lineNumber + 1))
      .join(' <- ');
    problems.push(
      'exception: ' + (details.exception?.description ?? details.text ?? 'unknown') +
        (where ? '\n           at ' + where : ''),
    );
  });
  page.on('Runtime.consoleAPICalled', (p) => {
    if (p.type !== 'error') return;
    const text = (p.args ?? []).map((a) => a.value ?? a.description ?? '').join(' ');
    problems.push('console.error: ' + text);
  });
  return problems;
}

/** Every request the page issues, with the response body kept for the ones we care about. */
function watchNetwork(page, interesting) {
  const seen = new Map();
  const bodies = new Map();
  page.on('Network.requestWillBeSent', (p) => {
    seen.set(p.requestId, { url: p.request.url, method: p.request.method, status: null });
  });
  page.on('Network.responseReceived', (p) => {
    const row = seen.get(p.requestId);
    if (row) row.status = p.response.status;
  });
  // Store the *promise* of each body, not the body.
  //
  // `Network.getResponseBody` is a round trip, and this handler cannot be awaited by the
  // caller. Storing the resolved value meant a check could read the map before the fetch
  // landed and quietly compare the page against an earlier response — which is exactly
  // what happened once the suite began running the same week twice on different ports.
  page.on('Network.loadingFinished', (p) => {
    const row = seen.get(p.requestId);
    if (!row || !interesting.test(row.url)) return;
    bodies.set(
      row.url,
      page
        .send('Network.getResponseBody', { requestId: p.requestId })
        .then((r) => r.body)
        .catch(() => null), // evicted; the status is still recorded
    );
  });
  return {
    requests: () => [...seen.values()],
    /**
     * The most recent response matching this pattern.
     *
     * Most recent, not first: the suite restarts the stack on a new port and drives some
     * weeks again, so `/weeks/1/run` legitimately matches twice. Returning the earlier one
     * would compare what is on screen now against a response from before the restart —
     * which for week 1 would quietly agree, and hide a real difference.
     */
    body: async (pattern) => {
      let found = null;
      for (const [url, body] of bodies) if (pattern.test(url)) found = body;
      return found === null ? null : await found;
    },
  };
}

/**
 * Record every state the status band passes through.
 *
 * Week 1 finishes in well under a second, so polling could easily step straight over the
 * "running" state and report an interface that never told the reader anything. An observer
 * installed before the click cannot miss it.
 */
const RECORDER = `
  window.__band = [];
  const note = () => {
    const el = document.querySelector('.statusBand');
    if (!el) return;
    const state = el.getAttribute('data-state');
    const text = (el.textContent || '').replace(/\\s+/g, ' ').trim();
    const last = window.__band[window.__band.length - 1];
    if (!last || last.state !== state) window.__band.push({ state, text });
    else last.text = text;
  };
  new MutationObserver(note).observe(document.body,
    { subtree: true, childList: true, attributes: true, characterData: true });
  note();
  return true;
`;

/** The visible text of the headings inside the result, in the order they are laid out. */
const HEADINGS = `
  return [...document.querySelectorAll('.feature h3')]
    .map((h) => (h.textContent || '').trim());
`;

/**
 * Drive one week the way a reader does, and check what came back is what was drawn.
 *
 * Representative rather than exhaustive: five weeks spread across the cumulative gate
 * exercise every distinct behaviour — the first, the middle, the last, and two in between
 * — without sixteen near-identical runs that would all fail together anyway.
 */
/**
 * Wait until React has actually attached to an element, not merely rendered it.
 *
 * The server-rendered HTML contains the button long before the handler exists, so a check
 * that waits for the element and then clicks is racing hydration — it passes on a fast
 * machine and fails on a slow one, and when it fails it looks like a broken toggle rather
 * than a fast test. React marks the nodes it owns with `__reactFiber$...` own properties,
 * which is the earliest moment a click will do anything.
 */
async function ready(page, selector) {
  await page.until(
    '(() => { const el = document.querySelector(' + JSON.stringify(selector) + ');' +
      " return !!el && Object.keys(el).some((k) => k.startsWith('__react')); })()",
    { what: 'React to hydrate ' + selector },
  );
}

/**
 * Switch experience mode, and say what the page looked like if it does not take.
 *
 * The toggle is two radio buttons and one attribute on `<html>`, so a click that fails to
 * change the mode has a small number of possible causes — the wrong button was under the
 * cursor, the buttons were not hydrated, or the viewport had collapsed to a layout where
 * they are not where they appear to be. A bare timeout distinguishes none of those, and a
 * flake that only reproduces inside a ten-minute suite is a flake nobody diagnoses.
 */
async function switchMode(page, want) {
  await ready(page, '.modeToggle__btn');

  // Ensure the mode, do not toggle it. Clicking the unchecked button unconditionally
  // switches *away* when the page is already in the mode being asked for — and the page
  // often is, because the stored preference is applied a moment after React attaches, so
  // "which button is unchecked" is not settled at the instant hydration completes.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const mode = await page.eval(
      "return document.documentElement.getAttribute('data-mode');",
    );
    if (mode === want) return;
    await page.click('.modeToggle__btn[aria-checked="false"]');
    const deadline = Date.now() + 8000;
    while (Date.now() < deadline) {
      const now = await page.eval(
        "return document.documentElement.getAttribute('data-mode');",
      );
      if (now === want) return;
      await sleep(100);
    }
  }

  const state = await page.eval(`
    return {
      mode: document.documentElement.getAttribute('data-mode'),
      stored: (() => { try { return localStorage.getItem('aegis.experienceMode'); }
                       catch (e) { return 'unreadable'; } })(),
      viewport: [window.innerWidth, window.innerHeight],
      buttons: [...document.querySelectorAll('.modeToggle__btn')].map((b) => {
        const r = b.getBoundingClientRect();
        return {
          text: (b.textContent || '').trim().slice(0, 10),
          checked: b.getAttribute('aria-checked'),
          hydrated: Object.keys(b).some((k) => k.startsWith('__react')),
          onTop: document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2) === b,
        };
      }),
    };
  `);
  throw new Error(
    'the toggle did not settle on ' + want +
    '\n           page state: ' + JSON.stringify(state),
  );
}

async function driveWeek(page, base, week, network) {
  const label = 'week ' + week;
  await page.goto(base + '/weeks/' + week);
  await page.until("document.querySelector('.feature__run') !== null", {
    what: 'the run button on /weeks/' + week,
  });
  await ready(page, '.feature__run');

  const before = await page.eval(`
    return {
      mode: document.documentElement.getAttribute('data-mode'),
      tiles: document.querySelectorAll('.feature__headline .tile').length,
      band: !!document.querySelector('.statusBand'),
      index: (document.querySelector('.marketStrip__name') || {}).textContent || '',
    };
  `);
  check(
    label + ': opens in product mode with the NIFTY 50 context and no result yet',
    before.mode === 'product' && before.tiles === 0 && !before.band &&
      /nifty\s*50/i.test(before.index),
    JSON.stringify(before),
  );

  await page.click('.feature__run');
  const settled = await page.until(
    "(() => { const el = document.querySelector('.statusBand');" +
      " const s = el && el.getAttribute('data-state');" +
      " return s && s !== 'running' ? s : null; })()",
    { timeoutMs: 300000, every: 200, what: label + ' finishing its run' },
  );
  check(
    label + ': the run started by the click finishes successfully',
    settled === 'done',
    'the band settled on "' + settled + '"',
  );

  const raw = await network.body(new RegExp('/weeks/' + week + '/run$'));
  const payload = raw ? JSON.parse(raw) : null;
  check(
    label + ': the backend answered the click with a result',
    payload !== null && payload.backend === 'reachable' && payload.status === 'OK',
    payload ? 'status=' + payload.status + ' backend=' + payload.backend : 'no response captured',
  );

  const shown = await page.eval(`
    const visible = (root) => [...root.childNodes].map((n) =>
      n.nodeType === 3 ? n.textContent
        : (n.checkVisibility && n.checkVisibility()) ? visible(n) : ''
    ).join('').replace(/\\s+/g, ' ').trim();
    return {
      tiles: [...document.querySelectorAll('.feature__headline .tile')].map((t) => ({
        label: (t.querySelector('.tile__label') || {}).textContent || '',
        value: ((t.querySelector('.tile__value') || {}).textContent || '').trim(),
      })),
      observations: [...document.querySelectorAll('.feature .observations li')]
        .map((li) => (li.textContent || '').trim()),
      evidence: document.querySelectorAll('.featureEvidence li').length,
      charts: document.querySelectorAll('.feature .featureChart').length,
      limitations: [...document.querySelectorAll('.featureLimits li')].map(visible),
      body: (document.body.textContent || '').replace(/\\s+/g, ' '),
    };
  `);

  check(
    label + ': headline figures are rendered with real values',
    shown.tiles.length > 0 && shown.tiles.every((t) => t.value && t.value !== '—'),
    JSON.stringify(shown.tiles),
  );

  const displays = new Set();
  const returned = new Set();
  for (const half of Object.values((payload && payload.results) || {})) {
    for (const m of half.metrics || []) displays.add(String(m.display));
    for (const o of half.observations || []) returned.add(o);
  }
  const strayFigures = shown.tiles.filter((t) => !displays.has(t.value));
  check(
    label + ': every figure on screen is in the bytes the browser received',
    strayFigures.length === 0,
    strayFigures.length ? 'not in the response: ' + JSON.stringify(strayFigures) : '',
  );
  const invented = shown.observations.filter((o) => !returned.has(o));
  check(
    label + ': every finding was written by a module, not by the page',
    invented.length === 0,
    invented.length ? 'not in the response: ' + JSON.stringify(invented) : '',
  );

  check(
    label + ': evidence and a chart are drawn with the result',
    shown.evidence > 0 && shown.charts > 0,
    'evidence rows=' + shown.evidence + ' charts=' + shown.charts,
  );

  // A week whose modules declare no limitation legitimately shows none, so the check is
  // that the page agrees with the response rather than that a list is always present.
  const declared = new Set();
  for (const half of Object.values((payload && payload.results) || {})) {
    for (const l of half.limitations || []) declared.add(l.id);
  }
  check(
    label + ': limitations on the page match the ones the modules returned',
    declared.size === 0
      ? shown.limitations.length === 0
      : shown.limitations.length === declared.size,
    'response ' + JSON.stringify([...declared]) + ' page ' + shown.limitations.length,
  );
  check(
    label + ': product mode shows limitation titles without the register codes',
    !/\bL-\d\d/.test(shown.limitations.join(' ')),
    shown.limitations.join(' | '),
  );

  const advisoryHits = ADVISORY
    .map((r) => (r.exec(scrubDisclaimer(shown.body)) || [])[0])
    .filter(Boolean);
  check(
    label + ': no advisory language on the rendered result',
    advisoryHits.length === 0,
    JSON.stringify(advisoryHits),
  );

  // Research mode is a view of the same result, not a recomputation of it.
  await switchMode(page, 'research');
  const research = await page.eval(`
    const visible = (root) => [...root.childNodes].map((n) =>
      n.nodeType === 3 ? n.textContent
        : (n.checkVisibility && n.checkVisibility()) ? visible(n) : ''
    ).join('').replace(/\\s+/g, ' ').trim();
    return {
      tiles: document.querySelectorAll('.feature__headline .tile').length,
      ids: [...document.querySelectorAll('.feature h4')]
        .map((h) => (h.textContent || '').trim()).join(' '),
      limitations: [...document.querySelectorAll('.featureLimits li')].map(visible),
    };
  `);
  const ids = ['STATS-' + String(week).padStart(2, '0'),
               'MULTIMODAL-' + String(week).padStart(2, '0')];
  check(
    label + ': research mode keeps the result and names the canonical modules',
    research.tiles === shown.tiles.length && ids.every((id) => research.ids.includes(id)),
    'tiles ' + shown.tiles.length + '->' + research.tiles + ' ids=' +
      JSON.stringify(research.ids.slice(0, 90)),
  );
  check(
    label + ': research mode reveals the limitation register codes',
    declared.size === 0 || research.limitations.some((l) => /L-\d\d/.test(l)),
    JSON.stringify(research.limitations),
  );

  await switchMode(page, 'product');
}

/** Whether a route is reachable, decided by what the page actually renders. */
async function reachable(page, base, path) {
  await page.goto(base + path);
  return page.eval(`
    const body = (document.body.textContent || '').replace(/\\s+/g, ' ');
    return {
      gated: /not enabled in this demonstration build/i.test(body),
      hasRunner: !!document.querySelector('.feature__run, .runPanel__go'),
      path: location.pathname,
    };
  `);
}


async function main() {
  let stack = null;
  const given = option('url');
  if (!given) {
    process.stdout.write('starting the analysis backend and the interface...\n');
    stack = await startStack();
  }
  let base16 = null;
  const base = given ?? stack.url;
  process.stdout.write('interface at ' + base + '\n\n');

  const chrome = await launch({ headless: !flag('headful') });
  process.stdout.write(chrome.version + '\n' + chrome.binary + '\n\n');

  const page = chrome.page;
  const problems = watchForErrors(page);
  const network = watchNetwork(page, /\/api\/aegis\//);

  // The inline boot script in app/layout.tsx is the only thing that stamps the mode and
  // theme onto <html> before the first paint; everything else happens at hydration. Read
  // the attributes at DOMContentLoaded, which is after that script and before React, so a
  // boot script that silently failed cannot be covered for by the provider that follows it.
  await page.send('Page.addScriptToEvaluateOnNewDocument', {
    source:
      "document.addEventListener('DOMContentLoaded', function () {" +
      "  window.__early = { mode: document.documentElement.dataset.mode," +
      "                     theme: document.documentElement.dataset.theme };" +
      '}, { once: true });',
  });

  try {
    // A dev server compiles a route the first time it is asked for. Warm it, then start
    // from a clean page so nothing below is measuring the compiler.
    await page.goto(base + '/weeks/1');
    await page.until("document.querySelector('.feature__run') !== null", {
      what: 'the run button on /weeks/1',
    });
    await page.goto(base + '/weeks/1');
    await page.until("document.querySelector('.feature__run') !== null", {
      what: 'the run button on /weeks/1',
    });
    await sleep(500);

    // ---------------------------------------------------------------- before ----
    const before = await page.eval(`
      const button = document.querySelector('.feature__run');
      return {
        label: (button.textContent || '').trim(),
        disabled: !!button.disabled,
        band: !!document.querySelector('.statusBand'),
        headline: document.querySelectorAll('.feature__headline .tile').length,
        idle: !!document.querySelector('.feature__idle'),
        mode: document.documentElement.getAttribute('data-mode'),
        question: (document.querySelector('.module__sub') || {}).textContent || '',
      };
    `);
    check('the page opens in product mode', before.mode === 'product', 'mode=' + before.mode);
    check(
      'the run button is present, enabled and asks to be pressed',
      !before.disabled && /run this analysis/i.test(before.label),
      JSON.stringify(before.label),
    );
    check(
      'nothing is shown as a result before anything has run',
      before.band === false && before.headline === 0 && before.idle === true,
      'band=' + before.band + ' tiles=' + before.headline + ' idle=' + before.idle,
    );

    // ------------------------------------------------------------- the click ----
    await page.eval(RECORDER);
    const box = await page.click('.feature__run');
    process.stdout.write(
      '\nclicked .feature__run at (' + Math.round(box.x) + ', ' + Math.round(box.y) +
        ') — ' + JSON.stringify(box.label) + '\n\n',
    );

    // Any terminal state ends the wait, not just success. A run that fails should be
    // reported as the failure it is rather than as a test that timed out.
    const settled = await page.until(
      "(() => { const el = document.querySelector('.statusBand');" +
        " const s = el && el.getAttribute('data-state');" +
        " return s && s !== 'running' ? s : null; })()",
      { timeoutMs: 180000, every: 60, what: 'the status band settling after the click' },
    );
    check(
      'the run the click started finished successfully',
      settled === 'done',
      'the band settled on "' + settled + '"',
    );

    const band = await page.eval('return window.__band;');
    const states = band.map((b) => b.state);
    check(
      'the click puts the page into a running state',
      states.includes('running'),
      'states seen: ' + JSON.stringify(states),
    );
    const running = band.find((b) => b.state === 'running');
    check(
      'while it runs the page says so, and counts',
      !!running && /running analysis/i.test(running.text) && /\d+s/.test(running.text),
      running ? JSON.stringify(running.text) : 'no running state recorded',
    );
    const done = band.find((b) => b.state === 'done');
    check(
      'when it finishes the page says the analysis is complete',
      !!done && /analysis complete/i.test(done.text),
      done ? JSON.stringify(done.text) : 'no done state recorded',
    );

    // --------------------------------------------------------- the request ----
    const runRequests = network
      .requests()
      .filter((r) => /\/api\/aegis\/weeks\/1\/run$/.test(r.url));
    check(
      'the click issues exactly one POST to the week-1 run endpoint',
      runRequests.length === 1 && runRequests[0].method === 'POST',
      JSON.stringify(runRequests),
    );
    check(
      'the backend answers it 200',
      runRequests[0]?.status === 200,
      'status=' + runRequests[0]?.status,
    );

    const raw = await network.body(/\/api\/aegis\/weeks\/1\/run$/);
    check('the response body was captured for comparison', !!raw);
    const payload = raw ? JSON.parse(raw) : null;
    check(
      'the backend was reachable, so this was computed and not a stored fallback',
      payload?.backend === 'reachable' && payload?.status === 'OK',
      'backend=' + payload?.backend + ' status=' + payload?.status,
    );
    const modes = Object.values(payload?.modes ?? {});
    check(
      'both halves of week 1 are labelled as live computation',
      modes.length === 2 && modes.every((m) => m === 'LIVE_COMPUTATION'),
      JSON.stringify(payload?.modes),
    );

    // ------------------------------------------------------------ the result ----
    const after = await page.eval(`
      const tiles = [...document.querySelectorAll('.feature__headline .tile')].map((t) => ({
        label: (t.querySelector('.tile__label') || {}).textContent || '',
        value: (t.querySelector('.tile__value') || {}).textContent || '',
      }));
      const visibleText = (root) => [...root.childNodes].map((n) =>
        n.nodeType === 3 ? n.textContent
          : (n.checkVisibility && n.checkVisibility()) ? visibleText(n) : ''
      ).join('').replace(/\\s+/g, ' ').trim();
      return {
        tiles,
        observations: [...document.querySelectorAll('.feature .observations li')]
          .map((li) => (li.textContent || '').trim()),
        limitations: [...document.querySelectorAll('.featureLimits li')]
          .map(visibleText),
        evidence: document.querySelectorAll('.featureEvidence li').length,
        charts: document.querySelectorAll('.feature .featureChart').length,
        basis: !!document.querySelector('.feature__basis'),
      };
    `);

    check(
      'headline figures are rendered with real values',
      after.tiles.length > 0 && after.tiles.every((t) => t.value.trim() && t.value !== '—'),
      JSON.stringify(after.tiles),
    );

    // The claim that matters: these numbers came out of that HTTP response.
    const displays = new Set();
    for (const half of Object.values(payload?.results ?? {})) {
      for (const metric of half.metrics ?? []) displays.add(String(metric.display));
    }
    const unmatched = after.tiles.filter((t) => !displays.has(t.value.trim()));
    check(
      'every figure on screen appears in the bytes the browser received',
      unmatched.length === 0,
      unmatched.length ? 'not in the response: ' + JSON.stringify(unmatched) : '',
    );

    const returned = new Set(
      Object.values(payload?.results ?? {}).flatMap((h) => h.observations ?? []),
    );
    const invented = after.observations.filter((o) => !returned.has(o));
    check(
      'every sentence under "What AEGIS found" was written by a module, not the page',
      invented.length === 0,
      invented.length ? 'not in the response: ' + JSON.stringify(invented) : '',
    );

    const headings = await page.eval(HEADINGS);
    const at = (pattern) => headings.findIndex((h) => pattern.test(h));
    const found = at(/what aegis found/i);
    const evidence = at(/evidence behind this/i);
    const limits = at(/how far this goes/i);
    check(
      'the result reads findings, then evidence, then limits',
      found >= 0 && evidence > found && limits > evidence,
      JSON.stringify(headings),
    );
    check(
      'the limitations are on the result itself, not only inside a disclosure',
      after.limitations.length > 0,
      JSON.stringify(after.limitations),
    );
    check('the evidence marks are drawn', after.evidence > 0, 'rows=' + after.evidence);
    check('a chart is drawn', after.charts > 0, 'elements=' + after.charts);
    check('the scientific framing sits below the result', after.basis === true);

    // --------------------------------------------------------------- research ----
    const productLimits = after.limitations.join(' ');
    check(
      'product mode shows limitation titles without the register codes',
      !/L-\d\d/.test(productLimits),
      productLimits,
    );

    await switchMode(page, 'research');
    const research = await page.eval(`
      const visibleText = (root) => [...root.childNodes].map((n) =>
        n.nodeType === 3 ? n.textContent
          : (n.checkVisibility && n.checkVisibility()) ? visibleText(n) : ''
      ).join('').replace(/\\s+/g, ' ').trim();
      return {
        limitations: [...document.querySelectorAll('.featureLimits li')]
          .map(visibleText),
        tiles: document.querySelectorAll('.feature__headline .tile').length,
        ids: [...document.querySelectorAll('.feature h4')]
          .map((h) => (h.textContent || '').trim()).join(' | '),
      };
    `);
    check(
      'switching to research does not discard the result',
      research.tiles === after.tiles.length,
      'tiles ' + after.tiles.length + ' -> ' + research.tiles,
    );
    check(
      'research mode reveals the limitation register codes',
      research.limitations.some((l) => /L-\d\d/.test(l)),
      JSON.stringify(research.limitations),
    );
    check(
      'research mode names the canonical module ids',
      /STATS-01/.test(research.ids) && /MULTIMODAL-01/.test(research.ids),
      JSON.stringify(research.ids),
    );

    // ------------------------------------------------------ a module page too ----
    await page.goto(base + '/stats/01');
    await page.until("document.querySelector('.runPanel__go') !== null", {
      what: 'the run button on /stats/01',
    });
    await sleep(400);
    await ready(page, '.runPanel__go');
    await page.click('.runPanel__go');
    await page.until(
      "!!document.querySelector('.runBadge')",
      { timeoutMs: 180000, every: 100, what: 'a result on /stats/01 after the click' },
    );
    const moduleRun = network
      .requests()
      .filter((r) => /\/api\/aegis\/modules\/STATS-01\/run$/.test(r.url));
    check(
      'the run button on a capability page reaches its own module endpoint',
      moduleRun.length === 1 && moduleRun[0].status === 200,
      JSON.stringify(moduleRun),
    );

    // ------------------------------------------------------- market context ----
    await page.goto(base + '/weeks/1');
    await page.until("document.querySelector('.feature__run') !== null", {
      what: 'the run button on /weeks/1',
    });

    const market = await page.eval(`
      const strip = document.querySelector('.marketStrip');
      return {
        present: !!strip,
        name: (document.querySelector('.marketStrip__name') || {}).textContent || '',
        level: (document.querySelector('.marketStrip__level') || {}).textContent || '',
        body: (document.body.textContent || '').replace(/\\s+/g, ' '),
      };
    `);
    check(
      'the NIFTY 50 market context appears on the weekly page',
      market.present && /nifty\s*50/i.test(market.name),
      JSON.stringify({ name: market.name, level: market.level }),
    );
    check(
      'the index carries a real level rather than a placeholder',
      /\d[\d,]*\.\d\d/.test(market.level),
      JSON.stringify(market.level),
    );
    // The proxy and the index are different instruments. The page is allowed to say so —
    // and does, in the footer — but must never attach one name to the other.
    check(
      'the liquidity proxy is never presented as the NIFTY 50',
      !/(liquidity|universe)\s+proxy[^.]{0,40}\bis\b[^.]{0,20}nifty/i.test(market.body),
      '',
      'a sentence on the page equates the proxy with the index',
    );

    const advisoryHits = ADVISORY
      .map((r) => (r.exec(scrubDisclaimer(market.body)) || [])[0])
      .filter(Boolean);
    check(
      'no advisory language appears on the rendered page',
      advisoryHits.length === 0,
      JSON.stringify(advisoryHits),
    );

    // ---------------------------------------------------------- the mode toggle ----
    // "Initially selected" means with no stored preference, so clear the one the earlier
    // checks left behind and reload. Reading it without that reads whatever this session
    // last chose — and reading it before hydration reads the server's default while the
    // boot script has already applied something else, which is how this check spent a
    // run asserting one thing and clicking another.
    await page.eval('localStorage.removeItem("aegis.experienceMode"); return true;');
    await page.goto(base + '/weeks/1');
    await ready(page, '.modeToggle__btn');

    const toggle = await page.eval(`
      const group = document.querySelector('.modeToggle');
      const buttons = [...document.querySelectorAll('.modeToggle__btn')];
      return {
        count: buttons.length,
        role: group ? group.getAttribute('role') : null,
        checked: buttons.map((b) => b.getAttribute('aria-checked')),
      };
    `);
    check(
      'both modes are offered on the one page, as a radio group',
      toggle.count === 2 && toggle.role === 'radiogroup',
      JSON.stringify(toggle),
    );
    check(
      'product is the mode initially selected',
      toggle.checked[0] === 'true' && toggle.checked[1] === 'false',
      JSON.stringify(toggle.checked),
    );

    await switchMode(page, 'research');
    await switchMode(page, 'product');
    check('clicking product switches the same page back', true);

    // The mode belongs to the reader, not to the page they happen to be on.
    await switchMode(page, 'research');
    await page.goto(base + '/stats/01');
    await page.until("document.querySelector('.runPanel__go') !== null", {
      what: '/stats/01 after navigating in research mode',
    });
    const carried = await page.eval(
      "return document.documentElement.getAttribute('data-mode');",
    );
    check(
      'the chosen mode survives navigating to another page',
      carried === 'research',
      'mode after navigation was ' + JSON.stringify(carried),
    );

    // ------------------------------------------------------ understand evidence ----
    await page.goto(base + '/weeks/1');
    await page.until("document.querySelector('.feature__run') !== null");
    await page.click('.feature__run');
    await page.until(
      "document.querySelector('.statusBand[data-state=\"done\"]') !== null",
      { timeoutMs: 180000, every: 60, what: 'the second run finishing' },
    );
    check(
      'the result carries an Understand evidence disclosure',
      await page.eval("return !!document.querySelector('details.feature__detail');"),
    );
    await page.click('details.feature__detail > summary');
    const opened = await page.until(
      "(() => { const d = document.querySelector('details.feature__detail');" +
        " return d && d.open && d.querySelectorAll('.feature__half').length; })()",
      { what: 'the disclosure opening onto both halves' },
    );
    check(
      'opening it reveals the full result from each half',
      opened === 2,
      'halves revealed: ' + opened,
    );
    check(
      'the evidence link reaches the alignment page',
      await page.eval(
        "return !!document.querySelector('.feature__basis a[href=\"/research/alignment\"]');",
      ),
    );

    // ------------------------------------------------------------- the week gate ----
    const activeWeek = await page.eval(`
      const m = document.cookie.match(/(?:^|;\\s*)aegis_active_week=(\\d+)/);
      return m ? Number(m[1]) : null;
    `);
    check(
      'the build reports itself as a week-1 demonstration',
      activeWeek === 1,
      'active week from the cookie: ' + activeWeek,
    );

    await page.goto(base + '/weeks/2');
    const gatedWeek = await page.eval(`
      const body = (document.body.textContent || '').replace(/\\s+/g, ' ');
      return {
        heading: ((document.querySelector('h1') || {}).textContent || '').trim(),
        url: location.pathname,
        run: !!document.querySelector('.feature__run'),
        tiles: document.querySelectorAll('.feature__headline .tile').length,
        mentionsWeek2: /week 2\\b/i.test(body),
        saysHow: /AEGIS_ACTIVE_WEEK|run\\.bat/i.test(body),
      };
    `);
    check(
      'a gated week does not render its feature',
      gatedWeek.run === false && gatedWeek.tiles === 0,
      JSON.stringify(gatedWeek),
    );
    check(
      'it says the capability is not enabled rather than showing an error',
      /not enabled/i.test(gatedWeek.heading) && gatedWeek.mentionsWeek2,
      JSON.stringify(gatedWeek.heading),
    );
    check(
      'it says how to enable it',
      gatedWeek.saysHow,
      '',
      'the page names neither the launcher nor the variable',
    );
    check(
      'the address the reader typed is kept rather than redirected away',
      gatedWeek.url === '/weeks/2',
      'landed on ' + gatedWeek.url,
    );

    const gatedModule = await page.eval(
      "const r = await fetch('/stats/02');" +
        'const t = await r.text();' +
        'return { status: r.status, gated: /not enabled/i.test(t),' +
        "         runner: t.includes('runPanel__go') };",
    );
    check(
      'a gated module page is gated too',
      gatedModule.gated && !gatedModule.runner,
      JSON.stringify(gatedModule),
    );

    // The gate has to hold when the interface is bypassed entirely.
    const directApi = await page.eval(`
      const out = {};
      for (const path of ['weeks/2/run', 'weeks/8/run', 'modules/STATS-08/run']) {
        const r = await fetch('/api/aegis/' + path, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const body = await r.text();
        let code = null;
        try { code = (JSON.parse(body).error || {}).code; } catch (e) { code = 'unparsed'; }
        out[path] = {
          status: r.status,
          code,
          leaks: /"metrics"|"observations"|"display"/.test(body),
        };
      }
      return out;
    `);
    for (const [path, result] of Object.entries(directApi)) {
      check(
        'calling ' + path + ' directly is refused, not answered',
        result.status === 403 && result.code === 'FEATURE_NOT_ENABLED' && !result.leaks,
        JSON.stringify(result),
      );
    }

    const week1StillWorks = await page.eval(`
      const r = await fetch('/api/aegis/weeks/1/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const body = await r.json();
      return { status: r.status, ok: body.status, modes: Object.values(body.modes || {}) };
    `);
    check(
      'the enabled week is unaffected by the gate',
      week1StillWorks.status === 200 &&
        week1StillWorks.ok === 'OK' &&
        week1StillWorks.modes.every((m) => m === 'LIVE_COMPUTATION'),
      JSON.stringify(week1StillWorks),
    );

    const context = await page.eval(`
      const out = {};
      for (const path of ['indices/NIFTY50', 'alignment', 'evidence/NIFTY50']) {
        const r = await fetch('/api/aegis/' + path);
        out[path] = r.status;
      }
      return out;
    `);
    check(
      'the market context is not gated along with the weeks',
      Object.values(context).every((s) => s === 200),
      JSON.stringify(context),
    );

    await page.goto(base + '/research/progress');
    const marks = await page.eval(`
      const rows = [...document.querySelectorAll('.progressGrid li')];
      return rows.map((li) => {
        const m = (li.textContent || '').match(/Week (\\d+)/);
        return {
          week: m ? Number(m[1]) : null,
          enabled: li.getAttribute('data-enabled'),
          linked: !!li.querySelector('a'),
        };
      });
    `);
    check(
      'research progress shows the whole programme and marks what is enabled',
      marks.length === 16 &&
        marks[0].enabled === 'true' &&
        marks.slice(1).every((m) => m.enabled === 'false'),
      JSON.stringify(marks.slice(0, 3)),
    );
    check(
      'a gated week is still named on the progress page, but not linked',
      marks[0].linked === true && marks.slice(1).every((m) => m.linked === false),
      'linked: ' + JSON.stringify(marks.map((m) => m.linked)),
    );

    // ------------------------------------------------- visible, locked, explained ----
    //
    // The product's shape does not shrink with the active week: a capability that has not
    // arrived stays in the navigation and says when it does. The three things that must
    // hold are that it looks deliberate, that it explains itself, and that reaching for it
    // moves nothing — no route change, no request, no result.

    // The capability progression is product navigation; research mode has its own list.
    // An earlier check left the page in research mode, and looking for a locked product
    // entry there finds nothing and says nothing useful about why.
    await page.goto(base + '/');
    await switchMode(page, 'product');
    await page.until(
      "(() => { const b = document.querySelector('.nav__link--locked');" +
        " return !!b && Object.keys(b).some((k) => k.startsWith('__react')); })()",
      { what: 'the navigation to render its locked capabilities' },
    );

    const navState = await page.eval(`
      return [...document.querySelectorAll('.nav__link')].map((n) => ({
        label: (n.textContent || '').replace(/[\\s\\u00a0]+/g, ' ').trim(),
        locked: n.classList.contains('nav__link--locked'),
        tag: n.tagName,
        ariaDisabled: n.getAttribute('aria-disabled'),
        requires: Number(n.getAttribute('data-requires-week')) || null,
        hasLockGlyph: !!n.querySelector('.nav__lock'),
      }));
    `);
    const lockedNav = navState.filter((n) => n.locked);
    check(
      'future capabilities stay in the navigation rather than disappearing',
      lockedNav.length > 0,
      'locked entries: ' + JSON.stringify(lockedNav.map((n) => n.requires)),
    );
    check(
      'every locked entry names a later week and carries a lock',
      lockedNav.every((n) => n.requires > 1 && n.hasLockGlyph),
      JSON.stringify(lockedNav.map((n) => ({ w: n.requires, lock: n.hasLockGlyph }))),
    );
    // `disabled` would swallow the click, and the click is how a reader finds out why.
    check(
      'a locked entry is an operable control, not a disabled one',
      lockedNav.every((n) => n.tag === 'BUTTON' && n.ariaDisabled === 'true'),
      JSON.stringify(lockedNav.map((n) => ({ tag: n.tag, aria: n.ariaDisabled }))),
    );
    check(
      'nothing in the navigation calls a finished capability unimplemented or broken',
      !/not implemented|unavailable|broken|error|coming in a research/i.test(
        navState.map((n) => n.label).join(' '),
      ),
      navState.map((n) => n.label).join(' | ').slice(0, 160),
    );

    const pathBefore = await page.eval('return location.pathname;');
    const callsBefore = network.requests().length;
    await page.click('.nav__link--locked');
    await sleep(800);
    const afterLockClick = await page.eval(`
      const t = document.querySelector('.lockedNotice');
      const visible = (root) => [...root.childNodes].map((n) =>
        n.nodeType === 3 ? n.textContent
          : (n.checkVisibility && n.checkVisibility()) ? visible(n) : ''
      ).join('').replace(/[\\s\\u00a0]+/g, ' ').trim();
      return {
        notice: t ? visible(t) : null,
        path: location.pathname,
        tiles: document.querySelectorAll('.tile__value').length,
      };
    `);
    check(
      'clicking a locked capability says "Coming soon" and names its week',
      !!afterLockClick.notice &&
        /coming soon/i.test(afterLockClick.notice) &&
        /week \d+/i.test(afterLockClick.notice),
      JSON.stringify(afterLockClick.notice),
    );
    check(
      'the notice never calls the capability unimplemented, missing or broken',
      !!afterLockClick.notice &&
        !/not implemented|not built|missing|broken|unavailable|404|FEATURE_NOT_ENABLED/i
          .test(afterLockClick.notice),
      JSON.stringify(afterLockClick.notice),
    );
    check(
      'clicking it does not navigate',
      afterLockClick.path === pathBefore,
      pathBefore + ' -> ' + afterLockClick.path,
    );
    const newCalls = network.requests().slice(callsBefore);
    check(
      'clicking it executes no backend request',
      newCalls.length === 0,
      JSON.stringify(newCalls.map((r) => r.method + ' ' + r.url)),
    );

    // Product mode keeps the register plain; research mode is where the mechanism belongs.
    const noticeRegisters = await page.eval(`
      const t = document.querySelector('.lockedNotice');
      const visible = (root) => [...root.childNodes].map((n) =>
        n.nodeType === 3 ? n.textContent
          : (n.checkVisibility && n.checkVisibility()) ? visible(n) : ''
      ).join('').replace(/[\\s\\u00a0]+/g, ' ').trim();
      return t ? visible(t) : '';
    `);
    check(
      'product mode keeps the environment variable out of the notice',
      !/AEGIS_ACTIVE_WEEK|enabled_from_week|capability registry/i.test(noticeRegisters),
      noticeRegisters.slice(0, 140),
    );

    await switchMode(page, 'research');
    const researchNotice = await page.eval(`
      const t = document.querySelector('.lockedNotice');
      const visible = (root) => [...root.childNodes].map((n) =>
        n.nodeType === 3 ? n.textContent
          : (n.checkVisibility && n.checkVisibility()) ? visible(n) : ''
      ).join('').replace(/[\\s\\u00a0]+/g, ' ').trim();
      return t ? visible(t) : '';
    `);
    check(
      'research mode explains that the capability exists and which week enables it',
      /implemented in the complete system/i.test(researchNotice) &&
        /running at week 1/i.test(researchNotice),
      researchNotice.slice(0, 180),
    );
    // The mode is a property of the reader, and the gate is a property of the server, so
    // switching view cannot move the line. Asserted rather than assumed: a loophole here
    // would defeat the whole arrangement, and "it is client-side so it must be fine" is
    // the reasoning that ships one.
    const inResearch = await page.eval(`
      const page16 = await fetch('/weeks/8');
      const html = await page16.text();
      const api = await fetch('/api/aegis/weeks/8/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const body = await api.text();
      return {
        mode: document.documentElement.getAttribute('data-mode'),
        pageGated: /coming soon|not enabled/i.test(html),
        pageHasRunner: /feature__run/.test(html),
        apiStatus: api.status,
        apiLeaks: /"metrics"|"observations"|"display"/.test(body),
      };
    `);
    check(
      'research mode is not a way past the lock',
      inResearch.mode === 'research' &&
        inResearch.pageGated === true &&
        inResearch.pageHasRunner === false &&
        inResearch.apiStatus === 403 &&
        inResearch.apiLeaks === false,
      JSON.stringify(inResearch),
    );
    await switchMode(page, 'product');

    // -------------------------------------------- locked is not the same as absent ----
    const unknown = await page.eval(`
      const r = await fetch('/weeks/99');
      const body = await r.text();
      return {
        status: r.status,
        comingSoon: /coming soon/i.test(body),
      };
    `);
    check(
      'a week the programme does not have is not found, not "coming soon"',
      unknown.status === 404 && unknown.comingSoon === false,
      JSON.stringify(unknown),
    );
    const unknownApi = await page.eval(`
      const r = await fetch('/api/aegis/weeks/99');
      let code = null;
      try { code = ((await r.clone().json()).error || {}).code; } catch (e) { code = 'unparsed'; }
      return { status: r.status, code };
    `);
    check(
      'the API agrees: an unknown week is UNKNOWN_WEEK, not FEATURE_NOT_ENABLED',
      unknownApi.status === 404 && unknownApi.code === 'UNKNOWN_WEEK',
      JSON.stringify(unknownApi),
    );

    const farFuture = await page.eval(`
      const r = await fetch('/weeks/16');
      const body = await r.text();
      return {
        status: r.status,
        comingSoon: /coming soon/i.test(body),
        leaks: /Noise floor|Comparisons tested|Seeds per configuration/i.test(body),
      };
    `);
    check(
      'a real future week says "coming soon" and leaks none of its result',
      farFuture.comingSoon === true && farFuture.leaks === false,
      JSON.stringify(farFuture),
    );


    // ------------------------------------------- /analysis, section by section ----
    //
    // The page is a permanent destination and must stay reachable; its sections are not.
    // The bug: at week 1 this page rendered MULTIMODAL-14's modality decomposition from a
    // static bundle while /weeks/14 was correctly refusing. Everything below is that bug.

    await page.goto(base + '/analysis');
    await page.until("document.querySelector('.home__section') !== null", {
      what: '/analysis to render',
    });

    const analysis = await page.eval(`
      const body = (document.body.textContent || '').replace(/[\\s\\u00a0]+/g, ' ');
      const html = document.documentElement.outerHTML;
      return {
        status: 200,
        lockedCards: document.querySelectorAll('.lockedSection').length,
        bars: document.querySelectorAll('.bars__row').length,
        // The week-14 result, in every form it could arrive in.
        values: /0\\.123913|0\\.113076|0\\.001115|0\\.005969/.test(html),
        keys: /total_auprc|"unique"|redundant_raw/.test(html),
        artifact: /decomposition\\.csv|modality_information_matrix/.test(html),
        saysComingSoon: /coming soon/i.test(body),
        modalities: [...document.querySelectorAll('.evidenceAvailability__list--wide li')]
          .map((li) => ({
            text: (li.textContent || '').replace(/[\\s\\u00a0]+/g, ' ').trim(),
            open: li.getAttribute('data-open'),
          })),
      };
    `);

    check(
      '/analysis stays reachable at week 1 — it is a permanent destination',
      analysis.lockedCards >= 0,
      'locked sections: ' + analysis.lockedCards,
    );
    check(
      'the week-14 contribution section is locked, not rendered',
      analysis.lockedCards > 0 && analysis.bars === 0 && analysis.saysComingSoon,
      JSON.stringify({
        locked: analysis.lockedCards,
        bars: analysis.bars,
        comingSoon: analysis.saysComingSoon,
      }),
    );
    check(
      'no week-14 result value reaches the page',
      analysis.values === false,
      'a decomposition value is present in the document',
    );
    check(
      'no week-14 metric key reaches the page',
      analysis.keys === false,
      'total_auprc / unique / redundant_raw is present in the document',
    );
    check(
      'no week-14 artifact path reaches the page',
      analysis.artifact === false,
      'the decomposition artifact is named in the document',
    );
    check(
      'the modality list reflects the demonstration week, not the experiment',
      analysis.modalities.length === 4 &&
        analysis.modalities.every((m) => m.open === 'false'),
      JSON.stringify(analysis.modalities.map((m) => m.text)),
    );

    // The static bundle is served straight off disk, so the page being clean is not
    // enough — the file itself has to refuse.
    const bundleAtOne = await page.eval(`
      const out = {};
      for (const f of ['modality_info.json', 'windows.json', 'weeks.json']) {
        const r = await fetch('/data/' + f);
        const text = await r.text();
        out[f] = { status: r.status, leaks: /0\\.123913|total_auprc/.test(text) };
      }
      return out;
    `);
    check(
      'a static bundle carrying a locked result is refused',
      bundleAtOne['modality_info.json'].status === 403 &&
        bundleAtOne['modality_info.json'].leaks === false,
      JSON.stringify(bundleAtOne['modality_info.json']),
    );
    check(
      'a bundle owned by no gated capability is still served',
      bundleAtOne['weeks.json'].status === 200,
      JSON.stringify(bundleAtOne['weeks.json']),
    );

    const analysisApi = await page.eval(`
      const out = {};
      for (const id of ['contribution-analysis', 'event-analysis',
                        'foundation-analysis', 'no-such-capability']) {
        const r = await fetch('/api/aegis/analysis/' + id);
        const text = await r.text();
        let code = null;
        try { code = ((JSON.parse(text).error) || {}).code; } catch (e) { code = 'unparsed'; }
        out[id] = {
          status: r.status,
          code,
          leaks: /0\\.123913|total_auprc/.test(text),
        };
      }
      return out;
    `);
    check(
      'the week-14 analysis API refuses, with nothing of the result in it',
      analysisApi['contribution-analysis'].status === 403 &&
        analysisApi['contribution-analysis'].code === 'FEATURE_NOT_ENABLED' &&
        analysisApi['contribution-analysis'].leaks === false,
      JSON.stringify(analysisApi['contribution-analysis']),
    );
    check(
      'an analysis capability that does not exist is unknown, not locked',
      analysisApi['no-such-capability'].status === 404 &&
        analysisApi['no-such-capability'].code === 'UNKNOWN_CAPABILITY',
      JSON.stringify(analysisApi['no-such-capability']),
    );

    // ------------------------------------------- the audio model, still locked ----
    //
    // AUDIO_MODEL_V1 is trained and its checkpoint is on disk. That is exactly why this
    // block matters: a capability must be gated because the week says so, not because the
    // implementation happens to be missing. Nothing of the model — not a class name, not
    // a metric, not the clip list — may reach a week-1 browser.
    const audioAtOne = await page.eval(`
      const html = document.documentElement.outerHTML;
      const body = (document.body.textContent || '').replace(/[\\s\\u00a0]+/g, ' ');
      const out = {
        locked: /Analyse a speech clip/i.test(body) && /coming soon/i.test(body),
        workspace: document.querySelector('.audioWork__pick') !== null,
        saysWeek: /available in week 7/i.test(body),
        // The model's own vocabulary, in any form it could arrive in.
        leaksClasses: /surprised|fearful|RAVDESS/i.test(html),
        leaksMetrics: /0[.]4708|0[.]4453|AUDIO_MODEL_V1/i.test(html),
      };
      for (const [key, url] of [['samples', '/api/aegis/multimodal/audio/samples'],
                                ['analyze', '/api/aegis/multimodal/analyze']]) {
        const r = await fetch(url, key === 'analyze'
          ? { method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ clip: 'anything' }) }
          : undefined);
        const text = await r.text();
        let code = null;
        try { code = ((JSON.parse(text).error) || {}).code; } catch (e) { code = 'unparsed'; }
        out[key] = { status: r.status, code,
                     leaks: /predicted|posterior|RAVDESS|surprised/i.test(text) };
      }
      const bundle = await fetch('/data/audio_model.json');
      out.bundle = { status: bundle.status,
                     leaks: /0[.]4708/.test(await bundle.text()) };
      return out;
    `);
    check(
      'the audio capability is visible and locked at week 1, not hidden',
      audioAtOne.locked === true && audioAtOne.workspace === false &&
        audioAtOne.saysWeek === true,
      JSON.stringify({ locked: audioAtOne.locked, workspace: audioAtOne.workspace,
                       saysWeek: audioAtOne.saysWeek }),
    );
    check(
      'no part of the trained audio model reaches a week-1 page',
      audioAtOne.leaksClasses === false && audioAtOne.leaksMetrics === false,
      JSON.stringify({ classes: audioAtOne.leaksClasses,
                       metrics: audioAtOne.leaksMetrics }),
    );
    check(
      'the audio sample list is refused with nothing of it in the refusal',
      audioAtOne.samples.status === 403 &&
        audioAtOne.samples.code === 'FEATURE_NOT_ENABLED' &&
        audioAtOne.samples.leaks === false,
      JSON.stringify(audioAtOne.samples),
    );
    check(
      'the audio inference endpoint refuses before it loads the model',
      audioAtOne.analyze.status === 403 &&
        audioAtOne.analyze.code === 'FEATURE_NOT_ENABLED' &&
        audioAtOne.analyze.leaks === false,
      JSON.stringify(audioAtOne.analyze),
    );
    check(
      'the audio scorecard bundle cannot be fetched directly at week 1',
      audioAtOne.bundle.status === 403 && audioAtOne.bundle.leaks === false,
      JSON.stringify(audioAtOne.bundle),
    );

    // ------------------------------------------- the video model, also still locked ----
    //
    // VIDEO_MODEL_V1 is trained and its checkpoint is on disk, which is why this matters:
    // the capability is gated because the week says so, not because the implementation is
    // missing. Nothing of the model may reach a week-1 browser, and the analyse endpoint
    // must refuse a video request even though the same endpoint serves audio.
    const videoAtOne = await page.eval(`
      const html = document.documentElement.outerHTML;
      const body = (document.body.textContent || '').replace(/[\\s\\u00a0]+/g, ' ');
      const out = {
        locked: /Analyse a video clip/i.test(body) && /coming soon/i.test(body),
        workspace: document.querySelector('.videoWork') !== null,
        saysWeek: /available in week 9/i.test(body),
        leaksFrames: /data:image[/]png/.test(html),
        leaksMetrics: /VIDEO_MODEL_V1|ExpressionVideoNet/i.test(html),
      };
      const samples = await fetch('/api/aegis/multimodal/video/samples');
      let code = null; const text = await samples.text();
      try { code = ((JSON.parse(text).error) || {}).code; } catch (e) { code = 'unparsed'; }
      out.samples = { status: samples.status, code,
                      leaks: /predicted|posterior|Actor_/i.test(text) };
      const analyse = await fetch('/api/aegis/multimodal/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modality: 'video', clip: 'anything' }),
      });
      const atext = await analyse.text();
      let acode = null;
      try { acode = ((JSON.parse(atext).error) || {}).code; } catch (e) { acode = 'unparsed'; }
      out.analyze = { status: analyse.status, code: acode,
                      required: (JSON.parse(atext) || {}).required_week,
                      leaks: /predicted|posterior/i.test(atext) };
      const bundle = await fetch('/data/video_model.json');
      out.bundle = { status: bundle.status };
      return out;
    `);
    check(
      'the video capability is visible and locked at week 1, not hidden',
      videoAtOne.locked === true && videoAtOne.workspace === false &&
        videoAtOne.saysWeek === true,
      JSON.stringify({ locked: videoAtOne.locked, workspace: videoAtOne.workspace,
                       saysWeek: videoAtOne.saysWeek }),
    );
    check(
      'no part of the trained video model reaches a week-1 page',
      videoAtOne.leaksFrames === false && videoAtOne.leaksMetrics === false,
      JSON.stringify({ frames: videoAtOne.leaksFrames,
                       metrics: videoAtOne.leaksMetrics }),
    );
    check(
      'the video take list is refused with nothing of it in the refusal',
      videoAtOne.samples.status === 403 &&
        videoAtOne.samples.code === 'FEATURE_NOT_ENABLED' &&
        videoAtOne.samples.leaks === false,
      JSON.stringify(videoAtOne.samples),
    );
    check(
      'a video analyse request is refused and names week 9',
      videoAtOne.analyze.status === 403 &&
        videoAtOne.analyze.code === 'FEATURE_NOT_ENABLED' &&
        videoAtOne.analyze.required === 9 &&
        videoAtOne.analyze.leaks === false,
      JSON.stringify(videoAtOne.analyze),
    );
    check(
      'the video scorecard bundle cannot be fetched directly at week 1',
      videoAtOne.bundle.status === 403,
      JSON.stringify(videoAtOne.bundle),
    );

    // --------------------------------------------- the fusion model, also locked ----
    //
    // Fusion needs both modalities and unlocks later than either. Its result is a
    // negative one, which makes leaking it doubly wrong: a week-1 reader would see a
    // finding about an experiment the demonstration has not reached.
    const fusionAtOne = await page.eval(`
      const html = document.documentElement.outerHTML;
      const body = (document.body.textContent || '').replace(/[\\s\\u00a0]+/g, ' ');
      const out = {
        locked: /Analyse a paired sample/i.test(body) && /coming soon/i.test(body),
        workspace: document.querySelector('.fusionWork') !== null,
        saysWeek: /available in week 14/i.test(body),
        leaksFinding: /below the audio model|FUSION_MODEL_V1/i.test(html),
      };
      const samples = await fetch('/api/aegis/multimodal/fusion/samples');
      const text = await samples.text();
      let code = null;
      try { code = ((JSON.parse(text).error) || {}).code; } catch (e) { code = 'unparsed'; }
      out.samples = { status: samples.status, code,
                      leaks: /PAIR-|below the audio/i.test(text) };
      const analyse = await fetch('/api/aegis/multimodal/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modality: 'fusion', pair: 'anything' }),
      });
      const atext = await analyse.text();
      let parsed = {};
      try { parsed = JSON.parse(atext); } catch (e) { parsed = {}; }
      out.analyze = { status: analyse.status, code: (parsed.error || {}).code,
                      required: parsed.required_week,
                      leaks: /predicted|posterior/i.test(atext) };
      return out;
    `);
    check(
      'the fusion capability is visible and locked at week 1, not hidden',
      fusionAtOne.locked === true && fusionAtOne.workspace === false &&
        fusionAtOne.saysWeek === true,
      JSON.stringify({ locked: fusionAtOne.locked, workspace: fusionAtOne.workspace,
                       saysWeek: fusionAtOne.saysWeek }),
    );
    check(
      'no part of the fusion experiment reaches a week-1 page',
      fusionAtOne.leaksFinding === false,
      JSON.stringify({ finding: fusionAtOne.leaksFinding }),
    );
    check(
      'the fusion sample list is refused with nothing of it in the refusal',
      fusionAtOne.samples.status === 403 &&
        fusionAtOne.samples.code === 'FEATURE_NOT_ENABLED' &&
        fusionAtOne.samples.leaks === false,
      JSON.stringify(fusionAtOne.samples),
    );
    check(
      'a fusion analyse request is refused and names week 14',
      fusionAtOne.analyze.status === 403 &&
        fusionAtOne.analyze.code === 'FEATURE_NOT_ENABLED' &&
        fusionAtOne.analyze.required === 14 &&
        fusionAtOne.analyze.leaks === false,
      JSON.stringify(fusionAtOne.analyze),
    );


    // ------------------------------------------------------- before hydration ----
    await page.goto(base + '/weeks/1?mode=research');
    await page.until('!!window.__early', { what: 'the document reaching DOMContentLoaded' });
    const early = await page.eval('return window.__early;');
    check(
      'a shared research link is already in research mode at first paint',
      early.mode === 'research',
      'mode at DOMContentLoaded was ' + JSON.stringify(early.mode),
    );
    check(
      'the theme is decided before the first paint too',
      early.theme === 'light' || early.theme === 'dark',
      'theme at DOMContentLoaded was ' + JSON.stringify(early.theme),
    );

    // ============================================================ phase two ====
    //
    // Everything above ran against a week-1 demonstration. The gate is cumulative, so
    // the remaining questions are about other points on it: do the later weekly features
    // actually work when they are switched on, and does each active week draw the line in
    // the right place. Both need a differently configured process, so the stack restarts.

    if (!given) {
      // -------------------------------------------- representative weekly features ----
      process.stdout.write('\n--- restarting with every week enabled ---\n\n');
      stack.stop();
      stack = await startStack(16);
      base16 = stack.url;
      await page.goto(base16 + '/weeks/1');
      await page.until("document.querySelector('.feature__run') !== null", {
        what: 'the interface after the restart',
      });

      for (const week of [1, 4, 8, 12, 16]) {
        await driveWeek(page, base16, week, network);
      }

      // ------------------------------------------------ the line, at three settings ----
      const atSixteen = {
        16: await reachable(page, base16, '/weeks/16'),
        1: await reachable(page, base16, '/weeks/1'),
      };
      check(
        'with every week enabled, week 16 is reachable',
        atSixteen[16].gated === false && atSixteen[16].hasRunner === true,
        JSON.stringify(atSixteen[16]),
      );

      const navAtSixteen = await page.eval(
        "return [...document.querySelectorAll('.nav__link--locked')]" +
          ".map((n) => (n.textContent || '').trim());",
      );
      check(
        'the complete build has no locked capabilities left',
        navAtSixteen.length === 0,
        JSON.stringify(navAtSixteen),
      );

      // ------------------------- the same section, once the week has been reached ----
      await page.goto(base16 + '/analysis');
      await page.until("document.querySelector('.home__section') !== null", {
        what: '/analysis with every week enabled',
      });
      const openAnalysis = await page.eval(`
        const html = document.documentElement.outerHTML;
        return {
          lockedCards: document.querySelectorAll('.lockedSection').length,
          bars: [...document.querySelectorAll('.bars__row')].map((r) => ({
            label: (r.querySelector('.bars__label') || {}).textContent || '',
            value: (r.querySelector('.bars__value') || {}).textContent || '',
          })),
          values: /0\\.123913|0\\.113076/.test(html),
          modalities: [...document.querySelectorAll('.evidenceAvailability__list--wide li')]
            .map((li) => li.getAttribute('data-open')),
        };
      `);
      check(
        'with the week reached, the contribution section renders its real result',
        openAnalysis.lockedCards === 0 && openAnalysis.bars.length > 0,
        JSON.stringify({
          locked: openAnalysis.lockedCards,
          bars: openAnalysis.bars.length,
        }),
      );
      check(
        'no measured contribution is rendered as a flat zero',
        openAnalysis.bars.every((b) => b.value.trim() !== '0%'),
        JSON.stringify(openAnalysis.bars),
      );
      check(
        'every kind of evidence is available once every week is reached',
        openAnalysis.modalities.length === 4 &&
          openAnalysis.modalities.every((m) => m === 'true'),
        JSON.stringify(openAnalysis.modalities),
      );

      const openApi = await page.eval(`
        const r = await fetch('/api/aegis/analysis/contribution-analysis');
        const body = await r.json();
        return {
          status: r.status,
          ok: body.status,
          metrics: (body.metrics || []).length,
          hasMeasurement: typeof body.measurement === 'string' && body.measurement.length > 0,
        };
      `);
      check(
        'the analysis API serves the real result once the week is reached',
        openApi.status === 200 && openApi.ok === 'OK' && openApi.metrics > 0 &&
          openApi.hasMeasurement,
        JSON.stringify(openApi),
      );

      const openBundle = await page.eval(`
        const r = await fetch('/data/modality_info.json');
        return { status: r.status };
      `);
      check(
        'the static bundle is served once its capability is open',
        openBundle.status === 200,
        JSON.stringify(openBundle),
      );


      process.stdout.write('\n--- restarting at week 8 ---\n\n');
      stack.stop();
      stack = await startStack(8);
      const base8 = stack.url;
      const atEight = {
        8: await reachable(page, base8, '/weeks/8'),
        9: await reachable(page, base8, '/weeks/9'),
        1: await reachable(page, base8, '/weeks/1'),
      };
      check(
        'at week 8, week 8 is reachable',
        atEight[8].gated === false && atEight[8].hasRunner === true,
        JSON.stringify(atEight[8]),
      );
      check(
        'at week 8, week 9 is not',
        atEight[9].gated === true && atEight[9].hasRunner === false,
        JSON.stringify(atEight[9]),
      );
      check(
        'at week 8, the earlier weeks stay reachable',
        atEight[1].gated === false && atEight[1].hasRunner === true,
        JSON.stringify(atEight[1]),
      );

      const apiAtEight = await page.eval(`
        const out = {};
        for (const w of [8, 9, 16]) {
          const r = await fetch('/api/aegis/weeks/' + w + '/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
          });
          out[w] = r.status;
        }
        return out;
      `);
      check(
        'at week 8, the API draws the same line as the routes',
        apiAtEight[8] === 200 && apiAtEight[9] === 403 && apiAtEight[16] === 403,
        JSON.stringify(apiAtEight),
      );

      // ------------------------------- the same capability, one week further on ----
      //
      // The point of the progression is that nothing about the capability changes when it
      // opens — no component is edited, no result is different. Only the answer to "is
      // this week enabled" moves, and the same entry stops being a locked control and
      // becomes a destination.
      const navAtEight = await page.eval(`
        return [...document.querySelectorAll('.nav__link')].map((n) => ({
          label: (n.textContent || '').replace(/[\\s\\u00a0]+/g, ' ').trim(),
          locked: n.classList.contains('nav__link--locked'),
          href: n.getAttribute('href'),
          requires: Number(n.getAttribute('data-requires-week')) || null,
        }));
      `);
      const detection = navAtEight.find((n) => /event detection/i.test(n.label));
      check(
        'a capability locked at week 1 is a destination at its own week',
        !!detection && detection.locked === false && detection.href === '/weeks/8',
        JSON.stringify(detection),
      );
      check(
        'nothing below the active week is still locked',
        navAtEight.filter((n) => n.locked).every((n) => n.requires > 8),
        JSON.stringify(navAtEight.filter((n) => n.locked).map((n) => n.requires)),
      );
      check(
        'the later capabilities are still locked at week 8',
        navAtEight.some((n) => n.locked),
        JSON.stringify(navAtEight.filter((n) => n.locked).map((n) => n.label)),
      );

      // Opening it must reach the real feature and run the real backend.
      await page.goto(base8 + '/weeks/8');
      await page.until("document.querySelector('.feature__run') !== null", {
        what: 'the week 8 feature after it was unlocked',
      });
      await ready(page, '.feature__run');
      const noNotice = await page.eval(
        "return document.querySelector('.lockedNotice') === null;",
      );
      check('no "coming soon" appears for a capability that is now open', noNotice);

      await page.click('.feature__run');
      const eightSettled = await page.until(
        "(() => { const el = document.querySelector('.statusBand');" +
          " const s = el && el.getAttribute('data-state');" +
          " return s && s !== 'running' ? s : null; })()",
        { timeoutMs: 300000, every: 200, what: 'week 8 finishing its run' },
      );
      const eightBody = await network.body(/\/weeks\/8\/run$/);
      const eightPayload = eightBody ? JSON.parse(eightBody) : null;
      check(
        'the unlocked capability runs its real backend',
        eightSettled === 'done' &&
          eightPayload &&
          eightPayload.status === 'OK' &&
          eightPayload.backend === 'reachable',
        JSON.stringify({
          band: eightSettled,
          status: eightPayload && eightPayload.status,
          modes: eightPayload && eightPayload.modes,
        }),
      );

      // ---------------------------------------- the audio workflow, now unlocked ----
      //
      // The same code that refused above, one week past its unlock. A person picks a
      // clip, presses Analyse, and the answer comes from the backend running the
      // checkpoint — which is why the run id is checked: a stored result would repeat.
      await page.goto(base8 + '/analysis');
      await page.until("document.querySelector('.audioWork__pick select') !== null", {
        what: 'the audio workspace after its capability opened',
      });
      await ready(page, '.audioWork__pick select');
      const offered = await page.eval(`
        const select = document.querySelector('.audioWork__pick select');
        return { options: select.options.length,
                 first: select.options[0] && select.options[0].textContent };
      `);
      check(
        'the workspace offers held-out clips to analyse',
        offered.options > 0 && /Actor_/.test(offered.first || ''),
        JSON.stringify(offered),
      );

      await page.click('.audioWork__pick .btn');
      await page.until("document.querySelector('.audioResult') !== null", {
        timeoutMs: 120000,
        what: 'the audio analysis to come back',
      });
      const runOne = await page.eval(`
        const body = (document.body.textContent || '').replace(/[\\s\\u00a0]+/g, ' ');
        return {
          heading: /Audio analysed/i.test(body),
          model: /AUDIO_MODEL_V1/.test(body),
          result: (document.querySelector('.audioResult__value--big') || {}).textContent,
          hasWhy: !!document.querySelector('.audioResult .btn--ghost'),
          evidence: document.querySelector('.audioEvidence') !== null,
        };
      `);
      check(
        'the workspace shows a real model result',
        runOne.heading && runOne.model &&
          /neutral|calm|happy|sad|angry|fearful|disgust|surprised/i.test(
            runOne.result || '',
          ) &&
          runOne.evidence === false,
        JSON.stringify(runOne),
      );

      const analyseBody = await network.body(/multimodal[\/]analyze$/);
      const analysePayload = analyseBody ? JSON.parse(analyseBody) : null;
      check(
        'the answer came from the backend running the checkpoint',
        analysePayload &&
          analysePayload.status === 'OK' &&
          analysePayload.model_id === 'AUDIO_MODEL_V1' &&
          /^AUD-/.test(analysePayload.run_id || '') &&
          (analysePayload.checkpoint_sha256 || '').length === 64,
        JSON.stringify({
          status: analysePayload && analysePayload.status,
          run: analysePayload && analysePayload.run_id,
          predicted: analysePayload && analysePayload.predicted,
        }),
      );
      check(
        'the result is described as the annotation, never as a state of mind',
        analysePayload &&
          /RAVDESS annotation/.test(analysePayload.task || '') &&
          /does not\s+measure a speaker/.test(analysePayload.note || ''),
        JSON.stringify(analysePayload && analysePayload.task),
      );

      await page.click('.audioResult .btn--ghost');
      await page.until("document.querySelector('.audioEvidence') !== null", {
        what: 'the evidence panel to open',
      });
      const evidence = await page.eval(`
        const body = (document.body.textContent || '').replace(/[\\s\\u00a0]+/g, ' ');
        return {
          method: /integrated gradients/i.test(body),
          regions: document.querySelectorAll('.audioEvidence__bars li').length,
          namesRun: /run AUD-/.test(body),
        };
      `);
      check(
        'Why opens evidence computed from that run',
        evidence.method && evidence.regions > 0 && evidence.namesRun,
        JSON.stringify(evidence),
      );

      // The cross-modality gate, on one endpoint. Audio unlocks at 7 and video at 9, so a
      // week-8 demonstration must serve audio and refuse video through the same route.
      // Getting this wrong would not look like a bug: it would look like a working page.
      const modalitiesAtEight = await page.eval(`
        const out = {};
        for (const modality of ['audio', 'video']) {
          const r = await fetch('/api/aegis/multimodal/analyze', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ modality, clip: 'whatever' }),
          });
          const text = await r.text();
          let parsed = {};
          try { parsed = JSON.parse(text); } catch (e) { parsed = {}; }
          out[modality] = { status: r.status, code: (parsed.error || {}).code,
                            required: parsed.required_week };
        }
        const samples = await fetch('/api/aegis/multimodal/video/samples');
        out.videoSamples = samples.status;
        return out;
      `);
      check(
        'at week 8 the same endpoint serves audio and refuses video',
        modalitiesAtEight.audio.status !== 403 &&
          modalitiesAtEight.video.status === 403 &&
          modalitiesAtEight.video.code === 'FEATURE_NOT_ENABLED' &&
          modalitiesAtEight.video.required === 9 &&
          modalitiesAtEight.videoSamples === 403,
        JSON.stringify(modalitiesAtEight),
      );

      const videoAtEight = await page.eval(`
        await fetch('/analysis');
        return true;
      `);
      check('the week 8 page still answered', videoAtEight === true);

      // ------------------------------------ the video workflow, one week further on ----
      process.stdout.write('\n--- restarting at week 9 ---\n\n');
      stack.stop();
      stack = await startStack(9);
      const base9 = stack.url;

      await page.goto(base9 + '/analysis');
      await page.until("document.querySelector('.videoWork select') !== null", {
        timeoutMs: 120000,
        what: 'the video workspace after its capability opened',
      });
      await ready(page, '.videoWork select');
      const takes = await page.eval(`
        const select = document.querySelector('.videoWork select');
        return { options: select.options.length,
                 first: select.options[0] && select.options[0].textContent };
      `);
      check(
        'the workspace offers held-out takes to analyse',
        takes.options > 0 && /Actor_/.test(takes.first || ''),
        JSON.stringify(takes),
      );

      await page.click('.videoWork .audioWork__pick .btn');
      const showedProgress = await page.eval(
        "return document.querySelector('.videoWork__progress') !== null;",
      );
      await page.until("document.querySelector('.audioResult') !== null", {
        timeoutMs: 180000,
        what: 'the video analysis to come back',
      });
      const videoRun = await page.eval(`
        const body = (document.body.textContent || '').replace(/[\\s\\u00a0]+/g, ' ');
        return {
          heading: /Video analysed/i.test(body),
          model: /VIDEO_MODEL_V1/.test(body),
          result: (document.querySelector('.audioResult__value--big') || {}).textContent,
          evidence: document.querySelector('.audioEvidence') !== null,
        };
      `);
      check(
        'the workspace shows a real model result',
        videoRun.heading && videoRun.model &&
          /neutral|calm|happy|sad|angry|fearful|disgust|surprised/i.test(
            videoRun.result || '',
          ) && videoRun.evidence === false,
        JSON.stringify(videoRun),
      );
      check(
        'the page said it was working while the model ran',
        showedProgress === true,
      );

      const videoBody = await network.body(/multimodal\/analyze$/);
      const videoPayload = videoBody ? JSON.parse(videoBody) : null;
      check(
        'the answer came from the backend running the video checkpoint',
        videoPayload &&
          videoPayload.status === 'OK' &&
          videoPayload.model_id === 'VIDEO_MODEL_V1' &&
          videoPayload.modality === 'video' &&
          /^VID-/.test(videoPayload.run_id || '') &&
          (videoPayload.checkpoint_sha256 || '').length === 64,
        JSON.stringify({
          status: videoPayload && videoPayload.status,
          run: videoPayload && videoPayload.run_id,
          predicted: videoPayload && videoPayload.predicted,
        }),
      );
      check(
        'the video result is described as the annotation, never as a state of mind',
        videoPayload &&
          /RAVDESS annotation/.test(videoPayload.task || '') &&
          /does not\s+measure a person/.test(videoPayload.note || ''),
        JSON.stringify(videoPayload && videoPayload.task),
      );

      await page.click('.audioResult .btn--ghost');
      await page.until("document.querySelector('.frameStrip') !== null", {
        what: 'the frame evidence to open',
      });
      const frames = await page.eval(`
        const body = (document.body.textContent || '').replace(/[\\s\\u00a0]+/g, ' ');
        const items = [...document.querySelectorAll('.frameStrip li')];
        return {
          method: /integrated gradients/i.test(body),
          frames: items.length,
          withImages: items.filter((li) => li.querySelector('img')).length,
          highlighted: items.filter((li) => li.getAttribute('data-top') === 'true').length,
          namesRun: /run VID-/.test(body),
        };
      `);
      check(
        'Why opens the actual frames, attributed from that run',
        frames.method && frames.frames >= 8 &&
          frames.withImages === frames.frames &&
          frames.highlighted > 0 && frames.namesRun,
        JSON.stringify(frames),
      );

      const audioStillAtNine = await page.eval(`
        const r = await fetch('/api/aegis/multimodal/audio/samples');
        return r.status;
      `);
      check(
        'audio is still available once video unlocks',
        audioStillAtNine === 200,
        String(audioStillAtNine),
      );

      // Three modalities, three weeks, one endpoint. At week 9 audio and video are open
      // and fusion — which needs both — is still refused.
      const threeAtNine = await page.eval(`
        const out = {};
        for (const modality of ['audio', 'video', 'fusion']) {
          const r = await fetch('/api/aegis/multimodal/analyze', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ modality, clip: 'whatever', pair: 'whatever' }),
          });
          let parsed = {};
          try { parsed = JSON.parse(await r.text()); } catch (e) { parsed = {}; }
          out[modality] = { status: r.status, code: (parsed.error || {}).code,
                            required: parsed.required_week };
        }
        return out;
      `);
      check(
        'at week 9 the endpoint serves audio and video and refuses fusion',
        threeAtNine.audio.status !== 403 && threeAtNine.video.status !== 403 &&
          threeAtNine.fusion.status === 403 &&
          threeAtNine.fusion.code === 'FEATURE_NOT_ENABLED' &&
          threeAtNine.fusion.required === 14,
        JSON.stringify(threeAtNine),
      );

      // ------------------------------------------- the fusion workflow at week 14 ----
      process.stdout.write('\\n--- restarting at week 14 ---\\n\\n');
      stack.stop();
      stack = await startStack(14);
      const base14 = stack.url;

      await page.goto(base14 + '/analysis');
      await page.until("document.querySelector('.fusionWork select') !== null", {
        timeoutMs: 120000,
        what: 'the fusion workspace after its capability opened',
      });
      await ready(page, '.fusionWork select');
      const fusionOffer = await page.eval(`
        const body = (document.body.textContent || '').replace(/[\\s\\u00a0]+/g, ' ');
        const select = document.querySelector('.fusionWork select');
        return {
          options: select.options.length,
          first: select.options[0] && select.options[0].textContent,
          showsFinding: /What the experiment found/i.test(body) &&
            /(below the audio model|beats audio alone)/i.test(body),
          modalityBoxes: document.querySelectorAll(
            '.fusionWork__modalities input[type=checkbox]').length,
        };
      `);
      check(
        'the workspace offers paired samples and states the measured finding',
        fusionOffer.options > 0 && /Actor_/.test(fusionOffer.first || '') &&
          fusionOffer.showsFinding === true && fusionOffer.modalityBoxes === 2,
        JSON.stringify(fusionOffer),
      );

      await page.click('.fusionWork .audioWork__pick .btn');
      await page.until("document.querySelector('.audioResult') !== null", {
        timeoutMs: 180000,
        what: 'the fusion analysis to come back',
      });
      const fusionRun = await page.eval(`
        const body = (document.body.textContent || '').replace(/[\\s\\u00a0]+/g, ' ');
        return {
          heading: /Sample analysed/i.test(body),
          model: /FUSION_MODEL_V[12]/.test(body),
          result: (document.querySelector('.audioResult__value--big') || {}).textContent,
          comparison: document.querySelectorAll('.fusionWork__compare > div').length,
        };
      `);
      check(
        'the workspace shows a real fusion result beside each modality alone',
        fusionRun.heading && fusionRun.model && fusionRun.comparison === 3 &&
          /neutral|calm|happy|sad|angry|fearful|disgust|surprised/i.test(
            fusionRun.result || '',
          ),
        JSON.stringify(fusionRun),
      );

      const fusionBody = await network.body(/multimodal\/analyze$/);
      const fusionPayload = fusionBody ? JSON.parse(fusionBody) : null;
      check(
        'the answer came from the backend running the fusion checkpoint',
        fusionPayload &&
          fusionPayload.status === 'OK' &&
          /^FUSION_MODEL_V[12]$/.test(fusionPayload.model_id || '') &&
          /^FUS?2?-[0-9A-F]{12}$/.test(fusionPayload.run_id || '') &&
          (fusionPayload.available_modalities || []).length === 2 &&
          (fusionPayload.checkpoint_sha256 || '').length === 64,
        JSON.stringify({
          status: fusionPayload && fusionPayload.status,
          run: fusionPayload && fusionPayload.run_id,
          modalities: fusionPayload && fusionPayload.available_modalities,
        }),
      );
      check(
        'the measured comparison against audio alone travels with the result',
        fusionPayload &&
          (fusionPayload.measured_finding || '').length > 40 &&
          fusionPayload.headline_metrics &&
          typeof fusionPayload.headline_metrics.audio_only_accuracy === 'number' &&
          typeof fusionPayload.headline_metrics.fusion_accuracy === 'number',
        JSON.stringify(fusionPayload && fusionPayload.headline_metrics),
      );

      // Turning a modality off is the interaction this workspace exists for.
      await page.eval(`
        const boxes = document.querySelectorAll(
          '.fusionWork__modalities input[type=checkbox]');
        boxes[1].click();
        return true;
      `);
      await page.click('.fusionWork .audioWork__pick .btn');
      await page.until(
        "(() => { const el = document.querySelector('.fusionWork__chip[data-on=\"false\"]');" +
        " return el ? true : null; })()",
        { timeoutMs: 180000, what: 'the audio-only run to come back' },
      );
      const audioOnlyBody = await network.body(/multimodal\/analyze$/);
      const audioOnly = audioOnlyBody ? JSON.parse(audioOnlyBody) : null;
      check(
        'dropping a modality is honoured and reported',
        audioOnly &&
          audioOnly.available_modalities.length === 1 &&
          audioOnly.available_modalities[0] === 'audio' &&
          audioOnly.missing_modalities[0] === 'video',
        JSON.stringify(audioOnly && {
          available: audioOnly.available_modalities,
          missing: audioOnly.missing_modalities,
        }),
      );

      await page.click('.audioResult .btn--ghost');
      await page.until("document.querySelector('.audioEvidence') !== null", {
        what: 'the fusion evidence to open',
      });
      const fusionEvidence = await page.eval(`
        const body = (document.body.textContent || '').replace(/[\\s\\u00a0]+/g, ' ');
        return {
          method: /(integrated gradients over both embeddings|gate, evaluated on this sample)/i
            .test(body),
          namesRun: /run FUS?2?-/.test(body),
          bars: document.querySelectorAll('.audioEvidence__bars li').length,
        };
      `);
      check(
        'Why opens a modality split computed from that run',
        fusionEvidence.method && fusionEvidence.namesRun && fusionEvidence.bars > 0,
        JSON.stringify(fusionEvidence),
      );


    }


    // ------------------------------------------------------------------ quiet ----
    const noisy = problems.filter(
      (p) => !/favicon|Download the React DevTools|Fast Refresh/i.test(p),
    );
    check(
      'the browser reported no errors during any of this',
      noisy.length === 0,
      noisy.slice(0, 5).join('\n         '),
    );
  } finally {
    await chrome.close();
    if (stack) stack.stop();
  }

  process.stdout.write(
    '\n' + (checks.length - failures) + ' of ' + checks.length + ' checks passed\n',
  );
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((error) => {
  process.stderr.write('\n' + (error?.stack ?? String(error)) + '\n');
  process.exit(2);
});
