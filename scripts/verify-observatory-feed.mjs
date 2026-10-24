import assert from 'node:assert/strict'
import { startEventReconciliation } from '../src/lib/observatoryFeed.ts'

const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const flush = async () => { for (let i = 0; i < 4; i++) await Promise.resolve() }
function fakeClock() {
  let now = 0, nextId = 0
  const intervals = new Map()
  return {
    now: () => now,
    every(callback, ms) { const id = ++nextId; intervals.set(id, { callback, ms, next: now + ms }); return () => intervals.delete(id) },
    advance(ms) {
      const end = now + ms
      while (true) {
        const next = [...intervals.values()].sort((a, b) => a.next - b.next)[0]
        if (!next || next.next > end) break
        now = next.next; next.next += next.ms; next.callback()
      }
      now = end
    },
    get size() { return intervals.size },
  }
}
const batch = (cursor, ids = [cursor]) => ({ events: ids.map(sequence => ({ id: `e-${sequence}`, sequence })), cursor, persistence: 'mongodb', transport: 'atlas_polling', stream_error: null, resync_required: false, server_time: '2026-10-24T16:30:00Z' })
function harness() {
  const clock = fakeClock(), requests = [], received = [], connections = [], errors = [], liveEvents = new Map()
  let cursor = 10, restarts = 0
  const controller = new AbortController()
  const feed = startEventReconciliation({
    clock, signal: controller.signal, getCursor: () => cursor,
    loadAfter: (after, signal) => { const pending = deferred(); requests.push({ after, signal, ...pending }); return pending.promise },
    onBatch: result => { received.push(result); result.events.forEach(event => liveEvents.set(event.id, event)); cursor = Math.max(cursor, result.cursor) },
    onConnection: state => connections.push(state), onError: error => errors.push(error), onStale: () => restarts++,
  })
  // A fake stream adapter models the real integration: opening alone does not
  // call markLive; parsed heartbeat/event frames do, before event deduplication.
  const stream = {
    open() {},
    status() { feed.markLive() },
    event(event) { feed.markLive(); liveEvents.set(event.id, event); cursor = Math.max(cursor, event.sequence) },
  }
  return { clock, requests, received, connections, errors, feed, controller, stream, liveEvents, get cursor() { return cursor }, get restarts() { return restarts } }
}

const test = harness()
test.stream.open()
assert.deepEqual(test.connections, [], 'Opening a socket is not proof of fresh stream data')
test.stream.status()
assert.deepEqual(test.connections, ['connected'])
test.clock.advance(15000)
assert.equal(test.requests.length, 1)
assert.equal(test.requests[0].after, 10)
test.clock.advance(15000)
assert.equal(test.requests.length, 1, 'A second tick cannot overlap an outstanding reconciliation')
assert.deepEqual(test.connections, ['connected', 'polling'], 'A silent stream is stale at 30 seconds')
assert.equal(test.restarts, 1)
// SSE can advance while an older reconciliation remains in flight.
test.stream.event({ id: 'e-13', sequence: 13 })
test.requests[0].resolve(batch(12, [11, 12]))
await flush()
assert.equal(test.cursor, 13, 'A late poll cannot regress the shared stream cursor')
assert.deepEqual([...test.liveEvents.keys()].sort(), ['e-11', 'e-12', 'e-13'])
assert.deepEqual(test.connections, ['connected', 'polling', 'connected'])

test.clock.advance(15000)
assert.equal(test.requests[1].after, 13, 'Catch-up begins from the latest shared cursor')
test.requests[1].reject(new Error('fixture network outage'))
await flush()
assert.equal(test.errors.length, 1)
test.clock.advance(15000)
assert.equal(test.requests.length, 3, 'A failed catch-up does not stop future reconciliation')
test.requests[2].resolve(batch(14))
await flush()
assert.equal(test.cursor, 14)
assert.equal(test.connections.at(-1), 'polling', 'Successful HTTP catch-up must not claim SSE recovered')
assert.equal(test.restarts, 2, 'A fresh heartbeat permits one restart for the next silent period')
test.clock.advance(15000)
test.requests[3].resolve(batch(14))
await flush()
assert.equal(test.restarts, 2, 'A silent stream does not cause an SSE restart loop')
test.stream.status()
assert.equal(test.connections.at(-1), 'connected')
const heartbeatUpdates = test.connections.length
test.stream.status()
assert.equal(test.connections.length, heartbeatUpdates + 1, 'A new heartbeat must repair any reconnecting status set by the stream adapter')

test.clock.advance(15000)
const pending = test.requests.at(-1)
const receivedBeforeStop = test.received.length, errorsBeforeStop = test.errors.length, requestsBeforeStop = test.requests.length
assert.equal(pending.signal.aborted, false)
test.controller.abort()
assert.equal(pending.signal.aborted, true)
assert.equal(test.clock.size, 0)
pending.resolve(batch(99))
await flush()
test.clock.advance(60000); test.stream.status(); await test.feed.reconcile(); test.feed.stop()
assert.equal(test.received.length, receivedBeforeStop, 'Late transport completion after unmount cannot publish')
assert.equal(test.errors.length, errorsBeforeStop)
assert.equal(test.requests.length, requestsBeforeStop)
assert.equal(test.cursor, 14)

const lateFailure = harness()
lateFailure.clock.advance(15000)
lateFailure.feed.stop()
lateFailure.requests[0].reject(new Error('late aborted transport'))
await flush()
assert.equal(lateFailure.errors.length, 0, 'A late rejection after cleanup must not surface a stale error')

const cancelled = new AbortController(); cancelled.abort()
const idleClock = fakeClock()
const idle = startEventReconciliation({ clock: idleClock, signal: cancelled.signal, getCursor: () => 0, loadAfter: () => { throw new Error('must not load') }, onBatch: () => assert.fail('must not publish'), onConnection: () => assert.fail('must not connect'), onError: () => assert.fail('must not error') })
idle.markLive(); await idle.reconcile()
assert.equal(idleClock.size, 0, 'Already-aborted setup must not schedule background work')
console.log('Observatory feed checks passed: durable catch-up, current cursor, no overlap, heartbeat-only liveness, bounded reconnects, recovery after errors and abort cleanup.')
