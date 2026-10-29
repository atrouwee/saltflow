// saltflow capture: the one piece that is not Python. Plays each path of a flow in the product's web dummy with
// Playwright WebKit, on a fresh page per path, and crops the surface that arrived at every
// step. Reads a job file written by capture.py, writes PNGs and a report. Never the whole screen when a pane is up.
//
//   node capture.mjs <job.json>
//
// The job: { url, viewport: [w, h], schemes: ['light', 'dark'], out, pane: '[role=dialog]', paths: [ { flow, run,
//   steps: [{ id, surface, aria, title, css, box: [x, y, w, h] in percent of the screen, place }],
//   actions: [ [drive actions before step 1], [before step 2], ... ] } ] }
import { createRequire } from 'node:module'
import { writeFileSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'

const job = JSON.parse(await (await import('node:fs/promises')).readFile(process.argv[2], 'utf8'))
// Playwright where capture.py found it (doctor.py says the order), else the product's own web app
let webkit
const require = createRequire(import.meta.url)
for (const load of [() => job.playwright && require(job.playwright), () => createRequire(join(job.web, 'package.json'))('playwright')]) {
  try { ({ webkit } = load() || {}); if (webkit) break } catch (e) { /* the next */ }
}
if (!webkit) {
  console.error('no playwright package. Fix: saltflow doctor --fix, or npm install playwright in the web app; then npx playwright install webkit')
  process.exit(3)
}

const report = { captured: [], disagree: [], undriven: [], errors: [] }
let browser
try { browser = await webkit.launch() } catch (e) {
  console.error('playwright could not start WebKit. Fix: npx playwright install webkit (on Linux: npx playwright install --with-deps webkit)\n' + String(e.message || e).split('\n')[0])
  process.exit(3)
}
const settle = ms => new Promise(r => setTimeout(r, ms))

// Where a person would tap: inside the topmost pane when one is up and holds a match, else anywhere.
async function scope(page, find) {
  const dialogs = page.locator(job.pane || '[role=dialog]')
  const n = await dialogs.count()
  if (n) {
    const inTop = find(dialogs.nth(n - 1))
    if (await inTop.count()) return inTop
  }
  return find(page)
}

async function target(page, a) {
  if (a.role) {
    const name = a.name && a.name.startsWith('^') ? new RegExp(a.name) : a.name
    const loc = await scope(page, root => root.getByRole(a.role, name ? { name, exact: a.exact ?? false } : {}))
    return a.nth != null ? loc.nth(a.nth) : loc.first()
  }
  let loc = page.locator(a.css)
  if (a.hasText) loc = loc.filter({ hasText: a.hasText })
  if (a.nth != null) loc = loc.nth(a.nth)
  return loc.first()
}

async function perform(page, a) {
  if (a.do === 'move') {                     // a derived drive: the control marked with the move, else the key declared for it
    const c = page.locator(`[data-move~="${a.id}"]`).first()
    if (await c.isVisible().catch(() => false)) return c.click({ timeout: 4000 })
    const key = await page.evaluate(id => { for (const e of document.querySelectorAll('[data-move-keys]')) for (const pr of e.getAttribute('data-move-keys').split(/\s+/)) { const [m, k] = pr.split(':'); if (m === id) return k } return null }, a.id)
    if (key) return page.keyboard.press(key)
    return c.click({ timeout: 4000 })
  }
  if (a.optional) { const l = page.locator(a.css).first(); if (!(await l.isVisible().catch(() => false))) return; return l.click({ timeout: 4000 }) }
  if (a.key) return page.keyboard.press(a.key)
  const d = a.do || 'click'
  if (d === 'press') return page.keyboard.press(a.text || 'Enter')
  if (d === 'drag') {
    // "by": [dx, dy] moves from the start instead of onto a target; "hold": true keeps the press (a lifted tab)
    const from = await (await target(page, a.from)).boundingBox()
    const to = a.by ? { x: from.x + a.by[0], y: from.y + a.by[1], width: from.width, height: from.height } : await (await target(page, a.to)).boundingBox()
    if (!from || !to) throw new Error('drag: an end is not on screen')
    await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2); await page.mouse.down()
    if (!a.by) await page.mouse.move(from.x + from.width / 2 + 12, from.y + from.height / 2, { steps: 4 })
    await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 12 })
    if (!a.hold) await page.mouse.up()
    return
  }
  const t = await target(page, a)
  await t.waitFor({ state: 'visible', timeout: 4000 })
  // a control the dummy shows but disables is a finding in words, not a timeout
  if (d === 'click' && await t.isDisabled().catch(() => false)) throw new Error(`the dummy disables ${a.name || a.text || a.css || a.role}: not usable here yet`)
  if (d === 'fill') return t.fill(a.text || '', { timeout: 4000 })
  if (d === 'longpress') { const b = await t.boundingBox(); await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await page.mouse.down(); await settle(700); await page.mouse.up(); return }
  return t.click({ timeout: 4000 })
}

async function snap(page, step, scheme, pathName) {
  const file = `${step.id}${scheme === 'dark' ? '.dark' : ''}.png`
  const dir = join(job.out, pathName.flow)
  mkdirSync(dir, { recursive: true })
  const dialogs = page.locator(job.pane || '[role=dialog]')
  const n = await dialogs.count()
  let aria = null, title = null, how
  // an overlay (a toast) sits over whatever pane is up: its own element wins over the topmost dialog
  const over = (step.stage || step.place === 'overlay') && step.css ? page.locator(step.css).first() : null
  if (over && await over.waitFor({ state: 'visible', timeout: 1500 }).then(() => true, () => false)) {
    aria = await over.getAttribute('aria-label')
    title = ((await over.textContent().catch(() => '')) || '').trim().split('\n')[0] || null
    await over.screenshot({ path: join(dir, file) }); how = 'css'
  } else if (n) {
    const top = dialogs.nth(n - 1)
    aria = await top.getAttribute('aria-label')
    title = await top.locator('h2, h3').first().textContent().catch(() => null)
    await top.screenshot({ path: join(dir, file) }); how = 'pane'
  } else if (step.css) {
    await page.locator(step.css).first().screenshot({ path: join(dir, file) }); how = 'css'
  } else {
    // the box is a percent of the app's root (the manifest's capture.root, e.g. the till inside its device frame), else of the viewport
    const r = job.root ? await page.locator(job.root).first().boundingBox() : null
    const base = r || { x: 0, y: 0, width: job.viewport[0], height: job.viewport[1] }
    const [x, y, w, h] = step.box
    await page.screenshot({ path: join(dir, file), clip: { x: base.x + x / 100 * base.width, y: base.y + y / 100 * base.height, width: w / 100 * base.width, height: h / 100 * base.height } }); how = r ? 'root-box' : 'box'
  }
  const wants = step.aria || step.title
  const agrees = !wants || (aria && aria === step.aria) || (title && step.title && title.trim().startsWith(step.title.replace(/<.*$/, '').trim()))
  // the moves the component itself offers here: every control marked data-move, read from the code's own render
  const moves = step.stage && over ? await over.locator('[data-move]').evaluateAll(els => [...new Set(els.flatMap(e => e.getAttribute('data-move').split(/\s+/).filter(Boolean)))]).catch(() => null) : null
  // everything on screen at this step: the page's chrome (a strip, a tab bar) and the components beside this one (the map
  // beside the step card); a move may be made from any of them
  const chrome = step.stage ? await page.evaluate(() => {
    const ids = new Set()
    for (const e of document.querySelectorAll('[data-move]')) if (e.getClientRects().length) for (const id of e.getAttribute('data-move').split(/\s+/)) id && ids.add(id)
    // a move that starts at a control it passes through (a tab, then a row): the first control is enough to begin it
    for (const e of document.querySelectorAll('[data-move-via]')) if (e.getClientRects().length) for (const id of e.getAttribute('data-move-via').split(/\s+/)) id && ids.add(id)
    // keys a component answers to, declared on it: data-move-keys="undo:Meta+z close:Escape"
    for (const e of document.querySelectorAll('[data-move-keys]')) if (e.getClientRects().length) for (const pair of e.getAttribute('data-move-keys').split(/\s+/)) { const id = pair.split(':')[0]; id && ids.add(id) }
    return [...ids]
  }).catch(() => null) : null
  // the words each control shows, from the code's own render: a move's trigger is the words on the button
  const words = step.stage ? await page.locator('[data-move]').evaluateAll(els => { const o = {}; for (const e of els) { if (!e.getClientRects().length) continue; const w = (e.getAttribute('data-words') || e.getAttribute('aria-label') || e.innerText || e.textContent || '').trim().split('\n')[0].slice(0, 80); for (const id of e.getAttribute('data-move').split(/\s+/)) if (id && w && !o[id]) o[id] = w } return o }).catch(() => null) : null
  const rec = { flow: pathName.flow, run: pathName.run, step: step.id, file: join(pathName.flow, file), scheme, how, aria, title: title && title.trim(), agrees, moves, chrome, words }
  report.captured.push(rec)
  if (!agrees && n) report.disagree.push({ ...rec, wanted: wants })
}

for (const scheme of job.schemes) {
  for (const p of job.paths) {
    const page = await browser.newPage({ viewport: { width: job.viewport[0], height: job.viewport[1] }, colorScheme: scheme, hasTouch: !!job.touch, isMobile: !!job.touch })
    try {
      await page.goto(p.url || job.url); await settle(600)
      for (let i = 0; i < p.steps.length; i++) {
        const acts = p.actions[i]
        // a terminal step is shown by its command's live output or its sketch, never typed into the page
        // the page's path ends there, without an error
        const typed = (acts || []).some(a => (a.do === 'press' && a.text && !a.css && !a.role))
        if (p.steps[i].client === 'terminal' || typed) { report.undriven.push({ flow: p.flow, run: p.run, step: p.steps[i].id, why: 'a terminal step: shown live by its command, or its sketch' }); break }
        if (acts === null) { report.undriven.push({ flow: p.flow, run: p.run, step: p.steps[i].id, why: 'no drive by nature' }); break }
        if (acts === undefined) { report.undriven.push({ flow: p.flow, run: p.run, step: p.steps[i].id, why: 'no drive' }); break }
        for (const a of acts) {
          try { await perform(page, a) } catch (e) { throw new Error(`${p.steps[i].id}: ${a.css || (a.role ? a.role + ' ' + (a.name || '') : '') || a.key || a.do}: ${String(e.message || e).split('\n')[0]}`) }
        }
        await settle(acts.length ? 650 : 150)
        if (p.steps[i].snap === false) continue
        if (p.steps[i].settle) await settle(p.steps[i].settle)
        await snap(page, p.steps[i], scheme, p)
      }
    } catch (e) {
      report.errors.push({ flow: p.flow, run: p.run, error: String(e.message || e).split('\n')[0] })
    } finally { await page.close() }
  }
}
await browser.close()
writeFileSync(job.report, JSON.stringify(report, null, 1))
console.log(`captured ${report.captured.length}, disagree ${report.disagree.length}, undriven ${report.undriven.length}, errors ${report.errors.length}`)
