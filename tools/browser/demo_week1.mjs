/**
 * Walk week 1 the way a reader does, and photograph every step.
 *
 * This is the demo script, not a test: it presses the same button `check_interactive.mjs`
 * presses, but it keeps the pictures and prints the numbers instead of asserting on them.
 * Everything it captures is a real page served by the real interface talking to the real
 * backend, so the screenshots cannot drift from what the product does.
 *
 *   node tools/browser/demo_week1.mjs --url http://127.0.0.1:3000 --out .next-check/demo
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { launch, sleep } from './cdp.mjs';

const argv = process.argv.slice(2);
const option = (name, fallback) => {
  const i = argv.indexOf('--' + name);
  return i >= 0 ? argv[i + 1] : fallback;
};

const BASE = option('url', 'http://127.0.0.1:3000');
const OUT = option('out', '.next-check/demo');
mkdirSync(OUT, { recursive: true });

const shots = [];

async function shoot(page, name, caption, { full = true } = {}) {
  const { data } = await page.send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: full,
    optimizeForSpeed: false,
  });
  const file = join(OUT, name + '.png');
  writeFileSync(file, Buffer.from(data, 'base64'));
  const kb = Math.round(Buffer.from(data, 'base64').length / 1024);
  shots.push({ name, caption, file, kb });
  process.stdout.write('  captured ' + name + '.png (' + kb + ' KB) — ' + caption + '\n');
}

const main = async () => {
  const chrome = await launch({ headless: true, windowSize: '1280,900' });
  const page = chrome.page;

  // A dark-on-light capture at a normal desktop width, so the screenshots look like the
  // product rather than like a test harness.
  await page.send('Emulation.setDeviceMetricsOverride', {
    width: 1280, height: 900, deviceScaleFactor: 2, mobile: false,
  });

  const captured = { run: null };
  page.on('Network.loadingFinished', async (p) => {
    try {
      const { body } = await page.send('Network.getResponseBody', { requestId: p.requestId });
      const parsed = JSON.parse(body);
      if (parsed && parsed.week === 1 && parsed.results) captured.run = parsed;
    } catch {
      /* not the payload we are after */
    }
  });

  try {
    process.stdout.write('\nopening ' + BASE + '/weeks/1\n');
    await page.goto(BASE + '/weeks/1');
    await page.until("document.querySelector('.feature__run') !== null", {
      what: 'the run button',
    });
    await page.goto(BASE + '/weeks/1');
    await page.until("document.querySelector('.feature__run') !== null", {
      what: 'the run button',
    });
    await sleep(800);

    await shoot(page, '1-before', 'Week 1 in product mode, before anything has run');

    // Catch the running state: freeze the first frame that shows it.
    await page.eval(`
      window.__shot = null;
      const grab = () => {
        const el = document.querySelector('.statusBand[data-state="running"]');
        if (el && !window.__shot) window.__shot = true;
      };
      new MutationObserver(grab).observe(document.body,
        { subtree: true, childList: true, attributes: true });
      return true;
    `);

    const box = await page.click('.feature__run');
    process.stdout.write('\nclicked "' + box.label + '"\n');
    await page.until('!!window.__shot', { timeoutMs: 30000, every: 15, what: 'the running state' });
    await shoot(page, '2-running', 'The moment after the click — the analysis is running', {
      full: false,
    });

    await page.until("document.querySelector('.statusBand[data-state=\"done\"]') !== null", {
      timeoutMs: 180000, every: 60, what: 'the analysis finishing',
    });
    await sleep(700);
    await shoot(page, '3-result', 'The result, in product mode');

    await page.eval("document.querySelector('.statusBand').scrollIntoView({block:'start'});");
    await sleep(300);
    await shoot(page, '4-result-top', 'Headline figures and what AEGIS found', { full: false });

    await page.click('.modeToggle__btn:not(.is-active)');
    await page.until("document.documentElement.getAttribute('data-mode') === 'research'", {
      what: 'research mode',
    });
    await sleep(600);
    await shoot(page, '5-research', 'The same result, in research mode');

    // The numbers, straight from the response the browser received.
    const shown = await page.eval(`
      return {
        tiles: [...document.querySelectorAll('.feature__headline .tile')].map((t) => ({
          label: (t.querySelector('.tile__label') || {}).textContent || '',
          value: (t.querySelector('.tile__value') || {}).textContent || '',
        })),
        observations: [...document.querySelectorAll('.feature .observations li')]
          .map((li) => (li.textContent || '').trim()),
      };
    `);

    writeFileSync(
      join(OUT, 'run.json'),
      JSON.stringify({ shown, response: captured.run }, null, 2),
    );

    process.stdout.write('\n--- what the page shows ---\n');
    for (const t of shown.tiles) {
      process.stdout.write('  ' + t.label.padEnd(28) + t.value + '\n');
    }
    process.stdout.write('\n--- what the modules observed ---\n');
    for (const o of shown.observations) process.stdout.write('  · ' + o + '\n');

    if (captured.run) {
      process.stdout.write('\n--- the response behind it ---\n');
      process.stdout.write('  status   ' + captured.run.status + '\n');
      process.stdout.write('  elapsed  ' + captured.run.elapsed_s + 's\n');
      process.stdout.write('  modes    ' + JSON.stringify(captured.run.modes) + '\n');
      for (const [id, half] of Object.entries(captured.run.results)) {
        process.stdout.write(
          '  ' + id.padEnd(15) + half.status + '  ' + half.mode_label +
            '  metrics=' + half.metrics.length + '  series=' + half.series.length +
            '  limits=' + half.limitations.map((l) => l.id).join(',') + '\n',
        );
      }
    }

    writeFileSync(join(OUT, 'shots.json'), JSON.stringify(shots, null, 2));
    process.stdout.write('\nwrote ' + shots.length + ' screenshots to ' + OUT + '\n');
  } finally {
    await chrome.close();
  }
};

main().catch((error) => {
  process.stderr.write('\n' + (error?.stack ?? String(error)) + '\n');
  process.exit(1);
});
