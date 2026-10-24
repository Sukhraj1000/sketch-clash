import assert from 'node:assert/strict'
import { createLatestRequest, comparisonsPermitLabels } from '../src/lib/latestRequest.ts'
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve=yes; reject=no }); return { promise, resolve, reject } }
const loader = createLatestRequest(), a = deferred(), b = deferred()
let oldSignal
const old = loader.run(signal => { oldSignal=signal; return a.promise })
const current = loader.run(() => b.promise)
assert.equal(oldSignal.aborted, true)
b.resolve({ job:'B', pairs:['B-pair'] })
assert.deepEqual(await current, {value:{job:'B',pairs:['B-pair']}})
a.resolve({ job:'A', pairs:['A-pair'] })
assert.equal(await old, null, 'A cannot replace B even if transport ignores cancellation')
const detail = deferred(), comparison = deferred()
const atomic = loader.run(() => Promise.all([detail.promise, comparison.promise]))
detail.resolve({ job:'B' }); comparison.reject(new Error('comparison unavailable'))
assert.ok('error' in await atomic, 'Never publish successful detail with failed comparisons')
const abandoned = deferred(), pending = loader.run(() => abandoned.promise)
loader.cancel(); abandoned.resolve('late after unmount'); assert.equal(await pending,null)
assert.equal(comparisonsPermitLabels(false,'candidate',[]),false)
assert.equal(comparisonsPermitLabels(true,'candidate',[]),false)
assert.equal(comparisonsPermitLabels(true,'candidate',[{}]),false)
assert.equal(comparisonsPermitLabels(true,'candidate',[{review:{preference:'tie'}}]),true)
assert.equal(comparisonsPermitLabels(true,'baseline',[]),true)
console.log('Review loading checks passed: stale/aborted responses, atomic failure, unmount and blind-review gates.')

// Optional real React lifecycle regression, using only fixture HTTP responses and
// an isolated Vite server. Run with --browser after installing Playwright, or set
// SKETCH_CLASH_PLAYWRIGHT to an existing Playwright module's absolute entry path.
if (process.argv.includes('--browser')) {
  const { pathToFileURL } = await import('node:url')
  const { createServer } = await import('vite')
  const { mkdtemp, rm } = await import('node:fs/promises')
  const { tmpdir } = await import('node:os')
  const { join } = await import('node:path')
  const playwrightModule = await import(process.env.SKETCH_CLASH_PLAYWRIGHT ? pathToFileURL(process.env.SKETCH_CLASH_PLAYWRIGHT).href : 'playwright')
  const { chromium } = playwrightModule.default ?? playwrightModule
  const root = new URL('..', import.meta.url).pathname
  const previewId = '\0review-preview-fixture'
  const entryId = '\0review-entry-fixture'
  const cacheDir = await mkdtemp(join(tmpdir(), 'sketch-clash-review-'))
  const server = await createServer({
    root, cacheDir, configFile: false, logLevel: 'error',
    server: { host: '127.0.0.1', port: 0 },
    plugins: [{
      name: 'isolated-review-regression', enforce: 'pre',
      resolveId(source, importer) {
        if (source === entryId) return entryId
        if (source === './CharacterPreview' && importer?.endsWith('/QualityConsole.tsx')) return previewId
      },
      load(id) {
        if (id === entryId) return `import React from 'react';
          import {createRoot} from 'react-dom/client';
          import QualityConsole from '/src/components/QualityConsole.tsx';
          createRoot(document.getElementById('root')).render(React.createElement(QualityConsole,{onClose(){}}));`
        if (id !== previewId && !id.endsWith('/CharacterPreview.tsx')) return
        return `import React, {useEffect, useRef} from 'react';
          export default function Preview({scope,onReport}) {
            const mount = useRef(null);
            if (mount.current === null) mount.current = ++window.__previewMounts;
            useEffect(() => () => { window.__previewUnmounts++; }, []);
            return React.createElement('button', {'data-preview-mount':mount.current,onClick:()=>onReport({status:'passed',checks:{bounds:true,finite:true,visible:true,animations:[]},errors:[]})}, 'Fixture render '+scope);
          }`
      },
      configureServer(instance) {
        instance.middlewares.use((req, res, next) => {
          if (req.url !== '/') return next()
          res.setHeader('Content-Type', 'text/html')
          res.end('<div id="root"></div><script type="module" src="/@id/__x00__review-entry-fixture"></script>')
        })
      },
    }],
    optimizeDeps: { include: ['react', 'react-dom/client', 'react/jsx-runtime', 'lucide-react'] },
    oxc: { jsx: { runtime: 'automatic' } },
  })
  let browser
  try {
    await server.listen()
    browser = await chromium.launch({ headless: true })
    const page = await browser.newPage()
    const errors = []
    page.on('pageerror', error => { errors.push(error.message); console.error(error.message) })
    await page.addInitScript(() => {
      window.__previewMounts = 0; window.__previewUnmounts = 0
      const nativeSetInterval = window.setInterval, nativeClearInterval = window.clearInterval
      window.setInterval = (callback, ms, ...args) => {
        if (ms === 8000) { window.__qualityPoll = callback; return -8000 }
        return nativeSetInterval(callback, ms, ...args)
      }
      window.clearInterval = id => { if (id === -8000) window.__qualityPoll = null; else nativeClearInterval(id) }
    })
    const jobs = ['A', 'B'].map(id => ({ id, kind: 'candidate', status: 'running' }))
    const fighter = { id: 'fixture', visual_spec: {} }
    const detailFor = id => ({ job: jobs.find(job => job.id === id), results: [] })
    const pairsFor = id => [{ id: `${id}-pair`, case_id: 'case', image_ref: 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', left: { result_id: `${id}-left`, fighter }, right: { result_id: `${id}-right`, fighter } }]
    const overview = { evaluation_paused: true, active: { active_version_id: 'baseline', revision: 1 }, versions: [], cases: [], queue: [], jobs, policy: {}, readiness: {} }
    let hold = false, failComparison = false, renderPosts = 0
    const held = []
    const fulfill = (route, data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url())
      if (url.pathname === '/api/quality/overview') return fulfill(route, overview)
      if (/\/results\/[^/]+\/render$/.test(url.pathname)) { renderPosts++; return fulfill(route, { saved: true }) }
      const match = url.pathname.match(/^\/api\/quality\/jobs\/(A|B)(\/comparison)?$/)
      if (match) {
        const data = match[2] ? pairsFor(match[1]) : detailFor(match[1])
        if (hold) { held.push({ route, data }); return }
        if (failComparison && match[2]) return fulfill(route, { detail: 'fixture comparison failure' }, 503)
        return fulfill(route, data)
      }
      throw new Error(`Unexpected fixture request: ${route.request().method()} ${url.pathname}`)
    })
    const until = async (condition, message) => {
      for (let i = 0; i < 100; i++) { if (await condition()) return; await new Promise(resolve => setTimeout(resolve, 20)) }
      throw new Error(message)
    }
    const release = async () => { hold = false; await Promise.all(held.splice(0).map(({ route, data }) => fulfill(route, data))) }
    const triggerPoll = () => page.evaluate(() => { if (!window.__qualityPoll) throw new Error('Missing real quality polling callback'); window.__qualityPoll() })
    const address = server.httpServer.address()
    await page.goto(`http://127.0.0.1:${address.port}/`)
    page.setDefaultTimeout(10000)
    await page.getByRole('button', { name: 'Compare', exact: true }).click()
    await page.getByLabel('Evaluation run').selectOption('A')
    const pair = page.locator('.quality-pair')
    await pair.getByLabel('Reviewer', { exact: true }).fill('Maya')
    await pair.getByLabel('Reason and context', { exact: true }).fill('Unfinished human comparison')
    await pair.getByRole('button', { name: 'Prefer A', exact: true }).click()
    const originalPair = await pair.elementHandle()
    const assertPreserved = async () => {
      assert.equal(await pair.getByLabel('Reviewer', { exact: true }).inputValue(), 'Maya')
      assert.equal(await pair.getByLabel('Reason and context', { exact: true }).inputValue(), 'Unfinished human comparison')
      assert.equal(await pair.getByRole('button', { name: 'Prefer A', exact: true }).getAttribute('aria-pressed'), 'true')
      assert.equal(await originalPair.evaluate(node => node === document.querySelector('.quality-pair')), true, 'PairReview must retain the same DOM instance')
      assert.deepEqual(await page.evaluate(() => [window.__previewMounts, window.__previewUnmounts]), [2, 0], 'RenderedResult children must not remount during refresh')
    }
    hold = true; await triggerPoll()
    await until(() => held.length === 2, 'Both poll responses must be held')
    await assertPreserved()
    await release()
    await until(async () => !(await page.getByText('Refreshing saved evidence… Your current review stays open.').count()), 'Poll must settle')
    await assertPreserved()

    hold = true
    await pair.getByRole('button', { name: 'Fixture render Option A' }).click()
    await until(() => renderPosts === 1 && held.length === 2, 'Render write must trigger an onSaved refresh')
    await assertPreserved()
    await release()
    await until(async () => !(await page.getByText('Refreshing saved evidence… Your current review stays open.').count()), 'Render-triggered refresh must settle')
    await assertPreserved()
    await pair.getByRole('button', { name: 'Fixture render Option A' }).click()
    assert.equal(renderPosts, 1, 'The retained RenderedResult must deduplicate its second report')

    failComparison = true; await triggerPoll()
    await page.getByText(/Refresh failed: fixture comparison failure/).waitFor()
    await assertPreserved()
    failComparison = false; hold = true
    await page.getByLabel('Evaluation run').selectOption('B')
    await until(() => held.length === 2, 'New selection must load its own atomic snapshot')
    assert.equal(await pair.count(), 0, 'A different selection must never display the previous job')
    await release()
    await pair.waitFor()
    assert.equal(await pair.getByLabel('Reviewer', { exact: true }).inputValue(), '', 'A new pair starts a separate human review')
    assert.equal(await originalPair.evaluate(node => node.isConnected), false)
    assert.deepEqual(errors, [])
    console.log('React browser regression passed: same-run polling, onSaved and failed refresh preserve review/preview instances; switching runs resets them.')
  } finally {
    await browser?.close()
    await server.close()
    await rm(cacheDir, { recursive: true, force: true })
  }
}
