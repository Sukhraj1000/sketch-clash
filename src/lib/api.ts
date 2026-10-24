import type { BattleEvent } from '../game/battle';
import type { Fighter } from '../types';
export type PendingFighter = {
  battle_id:string; player_slot:0|1; capture_id:string; image_hash:string;
  canonical_type_id:string; object_type:string; display_name:string; image_ref:string;
  archetype:'Quick'|'Power'|'Guard'; stats:{health:100;attack:number;defense:number;speed:number};
  visual_spec:Record<string,unknown>; validation:Record<string,unknown>[]; config_versions:Record<string,string>;
  output_id?:string; pipeline_version_id?:string; parent_output_id?:string;
  observed_object?:{canonical_type_id:string;label:string;visible_features?:string[]};
};
export type FeedbackInput = {
  idempotency_key:string; output_id:string; pipeline_version_id:string;
  recognition_verdict:'correct'|'corrected'|'unsure'; creative_verdict:'keep'|'change'|'skipped';
  correction_label?:string; reasons:string[]; comment?:string; shared_consent:boolean;
};
export type CorrectionInput = {
  idempotency_key:string; output_id:string; pipeline_version_id:string;
  kind:'factual'|'style'; canonical_label?:string; details?:string; reasons:string[];
};
export type BattleRecord = {
  id:string;request_id:string;world_id:string;status:'draft'|'ready'|'running'|'completed'|'cancelled'|'failed';
  pending_fighters:[PendingFighter|null,PendingFighter|null];confirmed_capture_ids:[string|null,string|null];active_capture_ids:[string|null,string|null];
  fighters:PendingFighter[];events:BattleEvent[];winner_slot:0|1|null;duration_ms:number|null;
  eligible_at:string|null;playback_mode:'normal'|'reduced'|'quick'|null;seed:number|null;engine_version:string|null;
  completion:{resident_ids:string[];new_resident_ids:string[];durable:boolean}|null;
  persistence:'mongodb'|'development_memory';
  pipeline_version_id?:string;
};
export type Health = {status:string;persistence:string;persistent:boolean;ai_paused?:boolean;ai_status?:'paused'|'configured'|'unconfigured';ai_pause_reason?:string|null;gemini:{configured:boolean;model:string};message?:string;world_id:string};
export class ApiError extends Error {
  code:string; status:number;
  constructor(message:string,code:string,status:number){super(message);this.code=code;this.status=status;}
}
export async function api<T>(path:string,init:RequestInit={},options:{timeoutMs?:number}={}):Promise<T>{
  const controller=new AbortController();
  const abort=()=>controller.abort();
  if(init.signal?.aborted) controller.abort();
  init.signal?.addEventListener('abort',abort,{once:true});
  // Capture preparation may make several paced requests. Other API operations
  // retain their normal bounded timeout; this does not raise Gemini's pace.
  const captureMutation=init.method==='POST'&&/\/captures(?:\/[^/]+\/(?:correct|select))?$/.test(path);
  const timeout=window.setTimeout(abort,options.timeoutMs??(captureMutation?600000:125000));
  try {
    const response=await fetch(`/api${path}`,{...init,signal:controller.signal,headers:{...(init.body instanceof FormData?{}:{'Content-Type':'application/json'}),...init.headers}});
    let data:any;
    try{data=await response.json();}catch{throw new ApiError('The local API is not responding. Start both servers with npm run dev.','api_unavailable',response.status);}
    if(!response.ok)throw new ApiError(data.error?.message??'The request could not be completed.',data.error?.code??'request_failed',response.status);
    return data as T;
  } catch(error){
    if(error instanceof ApiError)throw error;
    if(init.signal?.aborted)throw new DOMException('Cancelled','AbortError');
    throw new ApiError(controller.signal.aborted?'The request took too long. Retry the same photo.':'Could not reach the local API. Check that the backend is running.','connection_failed',0);
  } finally {window.clearTimeout(timeout);init.signal?.removeEventListener('abort',abort);}
}
export async function prepareCapture<T>(battleId:string,form:FormData,signal:AbortSignal):Promise<T>{
  const path=`/battles/${battleId}/captures`;
  try{return await api<T>(path,{method:'POST',body:form,signal});}
  catch(error){
    if(signal.aborted||!(error instanceof ApiError)||error.code!=='connection_failed')throw error;
    // A disconnected browser does not imply failed recognition. Read the saved
    // outcome by the same capture ID before asking the user to retry. Never
    // issue another paid POST automatically.
    const captureId=form.get('capture_id');
    if(typeof captureId!=='string'||!captureId)throw error;
    try{return await api<T>(`${path}/${encodeURIComponent(captureId)}`,{signal},{timeoutMs:15000});}
    catch(recoveryError){
      if(signal.aborted)throw recoveryError;
      if(recoveryError instanceof ApiError&&recoveryError.code==='capture_processing'){
        throw new ApiError('This photo is still queued or being checked. Slow mode spaces Gemini calls at least 60 seconds apart. Retry this photograph to recover the same capture; do not upload it again.','capture_processing',409);
      }
      throw error;
    }
  }
}
export const post=<T,>(path:string,body:unknown={})=>api<T>(path,{method:'POST',body:JSON.stringify(body)});
export const asFighter=(fighter:PendingFighter):Fighter=>({id: `${fighter.battle_id}-${fighter.player_slot}`,name:fighter.display_name,image:fighter.image_ref,subtitle:`${fighter.object_type.toUpperCase()} · ${fighter.archetype.toUpperCase()}`,side:fighter.player_slot,color:fighter.player_slot===0?'var(--coral)':'var(--mint)',kind:'photo',archetype:fighter.archetype});
export const asPair=(fighters:PendingFighter[]):[Fighter,Fighter]=>[asFighter(fighters[0]),asFighter(fighters[1])];
