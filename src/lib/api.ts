import type { BattleEvent } from '../game/battle';
import type { Fighter } from '../types';
import { cameraFighter } from './camera-combat.ts';
import type { CameraCombat, CombatProfile } from './camera-combat';
export type RoundTheme = {id:string;name:string;instructions:string;examples:string[];rotation_index:number|null;policy_version:string;enforced:boolean};
export type ThemeValidation = {theme_id:string;theme_name:string;policy_version:string;verdict:'eligible'|'outside_theme'|'uncertain';reason:string;evidence_labels:string[];basis:'recognition_identity_rules'};
export const LEGACY_THEME:RoundTheme={id:'everyday',name:'Everyday Objects',instructions:'Choose one real object around you. Both players share this brief.',examples:['mug','book','phone','shoe'],rotation_index:null,policy_version:'legacy-unrestricted',enforced:false};
export type PendingFighter = {
  battle_id:string; player_slot:0|1; capture_id:string; image_hash:string;
  canonical_type_id:string; object_type:string; display_name:string; image_ref:string;
  archetype:'Quick'|'Power'|'Guard'; stats:{health:100;attack:number;defense:number;speed:number};
  visual_spec:Record<string,unknown>; validation:Record<string,unknown>[]; config_versions:Record<string,string>;
  output_id?:string; pipeline_version_id?:string; parent_output_id?:string;
  observed_object?:{canonical_type_id:string;label:string;visible_features?:string[]};
  combat_profile?:CombatProfile;
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
  theme?:RoundTheme|null;
  id:string;request_id:string;world_id:string;status:'draft'|'ready'|'running'|'completed'|'cancelled'|'failed';
  pending_fighters:[PendingFighter|null,PendingFighter|null];confirmed_capture_ids:[string|null,string|null];active_capture_ids:[string|null,string|null];
  fighters:PendingFighter[];events:BattleEvent[];winner_slot:0|1|null;duration_ms:number|null;
  eligible_at:string|null;playback_mode:'normal'|'reduced'|'quick'|null;seed:number|null;engine_version:string|null;
  completion:{resident_ids:string[];new_resident_ids:string[];durable:boolean}|null;
  persistence:'mongodb'|'development_memory';
  pipeline_version_id?:string;
  combat?:CameraCombat|null;
  final_health?:[number,number];
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
export type CaptureProgress = {
  capture_id:string; status:'processing'|'complete'|'failed'; stage:string; message:string; updated_at:string;
  model?:string; attempt?:number;
  queue?:{wait_reason?:string|null;dispatch_wait_seconds?:number;min_dispatch_interval_seconds?:number;foreground_waiting?:number};
};
export type CaptureProgressListener = (progress:CaptureProgress|null)=>void;

function watchCaptureProgress(path:string,captureId:string,signal:AbortSignal,onProgress?:CaptureProgressListener){
  if(!onProgress||signal.aborted)return()=>{};
  const controller=new AbortController();
  let busy=false,stopped=false,registered=false;
  const stop=()=>{if(stopped)return;stopped=true;controller.abort();window.clearInterval(interval);signal.removeEventListener('abort',stop)};
  const poll=async()=>{
    if(stopped||busy)return;
    busy=true;
    try{
      const progress=await api<CaptureProgress>(`${path}/${encodeURIComponent(captureId)}/progress`,{signal:controller.signal},{timeoutMs:5000});
      if(stopped||controller.signal.aborted)return;
      if(progress.capture_id!==captureId||typeof progress.stage!=='string'||typeof progress.message!=='string'||!['processing','complete','failed'].includes(progress.status))throw new Error('Progress did not match this capture.');
      registered=true;onProgress(progress);
    }catch(error){
      if(stopped||controller.signal.aborted)return;
      // The upload can still be in transit before the backend registers its ID.
      // Once registered, losing that record is an unavailable progress read.
      if(!registered&&error instanceof ApiError&&error.status===404)return;
      onProgress(null);
    }finally{busy=false;}
  };
  const interval=window.setInterval(()=>void poll(),3000);
  signal.addEventListener('abort',stop,{once:true});
  return stop;
}
export async function prepareCapture<T>(battleId:string,form:FormData,signal:AbortSignal,onProgress?:CaptureProgressListener):Promise<T>{
  const path=`/battles/${battleId}/captures`;
  const captureId=form.get('capture_id');
  const stopProgress=typeof captureId==='string'&&captureId?watchCaptureProgress(path,captureId,signal,onProgress):()=>{};
  try{return await api<T>(path,{method:'POST',body:form,signal});}
  catch(error){
    if(signal.aborted||!(error instanceof ApiError)||error.code!=='connection_failed')throw error;
    // A disconnected browser does not imply failed recognition. Read the saved
    // outcome by the same capture ID before asking the user to retry. Never
    // issue another paid POST automatically.
    if(typeof captureId!=='string'||!captureId)throw error;
    try{return await api<T>(`${path}/${encodeURIComponent(captureId)}`,{signal},{timeoutMs:15000});}
    catch(recoveryError){
      if(signal.aborted)throw recoveryError;
      if(recoveryError instanceof ApiError&&recoveryError.code==='capture_processing'){
        throw new ApiError('This photo is still queued or being checked. Camera checks run independently of island pacing. Retry this photograph to recover the same capture; do not upload it again.','capture_processing',409);
      }
      if(recoveryError instanceof ApiError&&recoveryError.code==='capture_failed')throw recoveryError;
      throw error;
    }
  }finally{stopProgress();}
}
export const post=<T,>(path:string,body:unknown={})=>api<T>(path,{method:'POST',body:JSON.stringify(body)});
export const asFighter=(fighter:PendingFighter):Fighter=>cameraFighter(fighter);
export const asPair=(fighters:PendingFighter[]):[Fighter,Fighter]=>[asFighter(fighters[0]),asFighter(fighters[1])];
