import assert from 'node:assert/strict'
import { startIndependentPoll } from '../src/lib/independentPolling.ts'
const timers = new Map()
let next = 0
const turn = () => new Promise(resolve => setImmediate(resolve))
globalThis.window = {setInterval:fn=>{timers.set(++next, fn);return next},clearInterval:id=>timers.delete(id)}
const controller = new AbortController()
const results = []
let slowCalls = 0, fastCalls = 0, releaseSlow
const slow = startIndependentPoll(() => {slowCalls++;return new Promise(resolve=>{releaseSlow=resolve})}, value=>results.push(value), ()=>{}, controller.signal)
const fast = startIndependentPoll(async () => ++fastCalls, value=>results.push(value), ()=>{}, controller.signal)
await turn()
assert.deepEqual(results,[1], 'Fast source publishes without waiting for a slow peer')
for(const refresh of timers.values())refresh()
await turn()
assert.equal(slowCalls,1,'Pending source does not overlap itself')
assert.deepEqual(results,[1,2], 'Healthy sources continue their own cadence')
controller.abort();releaseSlow('stale');await turn()
assert.deepEqual(results,[1,2], 'Late results from an old filter/unmounted view cannot publish')
slow();fast();assert.equal(timers.size,0)
const errors=[];const fresh=new AbortController()
const stop=startIndependentPoll(async()=>{throw new Error('Unavailable')},()=>assert.fail(),error=>errors.push(error.message),fresh.signal)
await turn();assert.deepEqual(errors,['Unavailable']);stop()
console.log('Independent polling checks passed: immediate partial success, separate cadence, no overlap, stale-filter suppression and visible failures.')
