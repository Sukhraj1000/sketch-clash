import assert from 'node:assert/strict'
import { api, prepareCapture } from '../src/lib/api.ts'

const timers=[]
globalThis.window={setTimeout:(_fn,ms)=>{timers.push(ms);return timers.length},clearTimeout:()=>{}}
const form=new FormData()
form.append('capture_id','same-capture')
const signal=new AbortController().signal
const calls=[]
globalThis.fetch=async(path,init)=>{
  calls.push({path,method:init.method??'GET'})
  if(init.method==='POST')throw new TypeError('Connection interrupted')
  return {ok:true,json:async()=>({capture_id:'same-capture',status:'recognized'})}
}
const restored=await prepareCapture('battle',form,signal)
assert.equal(restored.status,'recognized')
assert.deepEqual(calls,[{path:'/api/battles/battle/captures',method:'POST'},{path:'/api/battles/battle/captures/same-capture',method:'GET'}])
assert.deepEqual(timers,[600000,15000])
calls.length=0
globalThis.fetch=async(path,init)=>{
  calls.push({path,method:init.method??'GET'})
  if(init.method==='POST')throw new TypeError('Connection interrupted')
  return {ok:false,status:409,json:async()=>({error:{code:'capture_processing',message:'Preparing'}})}
}
await assert.rejects(prepareCapture('battle',form,signal),{code:'capture_processing'})
assert.equal(calls.filter(call=>call.method==='POST').length,1,'Recovery never repeats a paid request automatically')
globalThis.fetch=async(_path,init)=>{
  if(init.method==='POST')throw new TypeError('Connection interrupted')
  return {ok:false,status:409,json:async()=>({error:{code:'capture_failed',message:'Recognition stopped without a saved result.'}})}
}
await assert.rejects(prepareCapture('battle',form,signal),{code:'capture_failed',message:'Recognition stopped without a saved result.'})
const cancelled=new AbortController()
globalThis.fetch=async()=>{cancelled.abort();throw new TypeError('Cancelled')}
await assert.rejects(prepareCapture('battle',form,cancelled.signal),{name:'AbortError'})
globalThis.fetch=async()=>({ok:true,json:async()=>({})})
await api('/health')
assert.equal(timers.at(-1),125000,'Ordinary API requests keep the original bound')
console.log('Capture recovery checks passed: bounded Slow wait, saved outcome recovery, no duplicate POST, cancellation and ordinary timeout.')
