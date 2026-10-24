import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { transformWithOxc } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { prepareCapture } from '../src/lib/api.ts'

const originalWindow = globalThis.window, originalFetch = globalThis.fetch
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })
const progress = (stage, extra = {}) => ({ capture_id: 'photo-1', status: 'processing', stage, message: `Saved ${stage} stage.`, updated_at: '2026-10-24T17:00:00Z', ...extra })
function harness() {
  const intervals = new Map(), timeoutLengths = [], calls = [], updates = [], reads = []
  let timer = 0
  const write = deferred(), controller = new AbortController()
  globalThis.window = {
    setTimeout: (_callback, ms) => { timeoutLengths.push(ms); return ++timer }, clearTimeout() {},
    setInterval: (callback, ms) => { assert.equal(ms, 3000); intervals.set(++timer, callback); return timer },
    clearInterval: id => intervals.delete(id),
  }
  globalThis.fetch = (path, init) => {
    calls.push({ path, method: init.method ?? 'GET', signal: init.signal })
    if (init.method === 'POST') {
      init.signal.addEventListener('abort', () => write.reject(new DOMException('Cancelled', 'AbortError')), { once: true })
      return write.promise
    }
    assert.equal(path, '/api/battles/battle-1/captures/photo-1/progress', 'Polling reads only this capture progress')
    const read = deferred(); reads.push({ ...read, signal: init.signal }); return read.promise
  }
  const form = new FormData(); form.append('capture_id', 'photo-1')
  const result = prepareCapture('battle-1', form, controller.signal, value => updates.push(value))
  return { calls, updates, reads, write, result, controller, intervals, timeoutLengths, tick() { [...intervals.values()].forEach(callback => callback()) } }
}
try {
  const test = harness()
  assert.deepEqual(test.calls.map(call => call.method), ['POST'])
  test.tick()
  test.reads[0].resolve(response({ error: { code: 'capture_not_found' } }, 404))
  await flush()
  assert.equal(test.updates.length, 0, 'Before registration, 404 is not a fabricated processing stage')
  test.tick(); test.tick()
  assert.equal(test.reads.length, 2, 'Progress polls never overlap')
  test.reads[1].resolve(response(progress('local_detection')))
  await flush()
  assert.equal(test.updates.at(-1).stage, 'local_detection')
  test.tick()
  test.reads[2].resolve(response(progress('queued', { model: 'fixture-model', queue: { dispatch_wait_seconds: 42, min_dispatch_interval_seconds: 60 } })))
  await flush()
  assert.equal(test.updates.at(-1).stage, 'queued')
  test.tick()
  test.reads[3].resolve(response(progress('gemini_recognition', { capture_id: 'another-photo' })))
  await flush()
  assert.equal(test.updates.at(-1), null, 'Another capture cannot supply this photograph’s progress')
  test.tick()
  test.reads[4].resolve(response({ error: { code: 'storage_unavailable', message: 'Fixture unavailable' } }, 503))
  await flush()
  assert.equal(test.updates.at(-1), null)
  assert.equal(test.calls.filter(call => call.method === 'POST').length, 1, 'Unavailable progress never resubmits a paid request')
  test.tick()
  test.reads[5].resolve(response(progress('gemini_recognition')))
  await flush()
  assert.equal(test.updates.at(-1).stage, 'gemini_recognition', 'Progress reading recovers after an independent failure')
  test.tick()
  const late = test.reads[6], updateCount = test.updates.length
  test.write.resolve(response({ capture_id: 'photo-1', status: 'recognized' }))
  assert.equal((await test.result).status, 'recognized')
  assert.equal(test.intervals.size, 0)
  assert.equal(late.signal.aborted, true)
  late.resolve(response(progress('queued')))
  await flush()
  assert.equal(test.updates.length, updateCount, 'A late progress response cannot overwrite the completed capture')
  assert.equal(test.timeoutLengths[0], 600000, 'The existing bounded Slow wait remains unchanged')
  assert.ok(test.timeoutLengths.slice(1).every(ms => ms === 5000), 'Progress reads have their own short timeout')

  const cancelled = harness()
  cancelled.tick()
  const rejected = assert.rejects(cancelled.result, { name: 'AbortError' })
  cancelled.controller.abort()
  await rejected
  cancelled.reads[0].resolve(response(progress('queued')))
  await flush()
  assert.equal(cancelled.updates.length, 0, 'Leaving or replacing a capture suppresses old progress')
  assert.equal(cancelled.reads[0].signal.aborted, true)
  assert.equal(cancelled.intervals.size, 0)
  assert.equal(cancelled.calls.filter(call => call.method === 'POST').length, 1)

  // Render the actual status panel. The unused fighter-review/WebGL import is
  // replaced to keep this isolated presentation test independent of a GPU.
  const component = new URL('../src/components/CaptureStudio.tsx', import.meta.url)
  const transformed = await transformWithOxc(readFileSync(component, 'utf8'), component.pathname, { jsx: { runtime: 'automatic' } })
  let code = transformed.code.replace(/^\s*import\s+['"][^'"]+\.css['"];?\s*$/gm, '')
  const replacements = {
    '../lib/api': new URL('../src/lib/api.ts', import.meta.url).href,
    '../lib/imageInput': new URL('../src/lib/imageInput.ts', import.meta.url).href,
    '../lib/captureTimer': new URL('../src/lib/captureTimer.ts', import.meta.url).href,
    './FighterReview': 'data:text/javascript,export default function UnusedReview(){return null}',
    react: import.meta.resolve('react'), 'react/jsx-runtime': import.meta.resolve('react/jsx-runtime'), 'lucide-react': import.meta.resolve('lucide-react'),
  }
  for (const [specifier, resolved] of Object.entries(replacements)) code = code.replaceAll(JSON.stringify(specifier), JSON.stringify(resolved))
  const { CaptureProgressPanel } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
  const render = (value, extra = {}) => renderToStaticMarkup(createElement(CaptureProgressPanel, { normalizing: false, progress: value, unavailable: false, seconds: 140, ...extra }))
  const awaiting = render(null)
  assert.match(awaiting, /No preparation stage has been reported yet/)
  assert.match(awaiting, /Elapsed 2m 20s/)
  assert.doesNotMatch(awaiting, /GEMINI IS READING|WAITING FOR GEMINI/)
  const queued = render(progress('queued', { queue: { dispatch_wait_seconds: 42, min_dispatch_interval_seconds: 60 } }))
  assert.match(queued, /WAITING FOR GEMINI/)
  assert.match(queued, /not a completion estimate/)
  assert.doesNotMatch(queued, /GEMINI IS READING YOUR OBJECT/)
  assert.match(render(progress('local_ocr')), /READING VISIBLE TEXT LOCALLY/)
  assert.match(render(progress('gemini_recognition')), /GEMINI IS READING YOUR OBJECT/)
  const unavailable = render(progress('queued'), { unavailable: true })
  assert.match(unavailable, /PROGRESS UNAVAILABLE/)
  assert.doesNotMatch(unavailable, /WAITING FOR GEMINI|Saved queued stage/)
  assert.match(render(progress('validation')), /CHECKING THE FIGHTER/)
  assert.match(render(progress('saving')), /SAVING YOUR FIGHTER/)
  assert.match(render(progress('failed', { status: 'failed' })), /PREPARATION STOPPED/)
  console.log('Capture progress checks passed: saved stages, queue versus Gemini, independent read failure, no duplicate POST, no overlap, cancellation/late-read guards and actual panel rendering.')
} finally {
  globalThis.window = originalWindow
  globalThis.fetch = originalFetch
}
