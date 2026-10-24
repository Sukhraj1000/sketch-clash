import { lazy, Suspense, useRef, useState } from 'react'
import { ArrowRight, Check, CheckCircle2, HelpCircle, RefreshCw, SlidersHorizontal } from 'lucide-react'
import type { CorrectionInput, FeedbackInput } from '../lib/api'
import type { CaptureResponse } from './CaptureStudio'
import type { WorldCharacter } from './WorldView'
import './FighterReview.css'

const CharacterPreview = lazy(() => import('./CharacterPreview'))
const REASONS = [
  ['resemblance', 'Does not resemble my object'], ['colour_proportions', 'Colour or proportions'],
  ['name', 'Name'], ['style_accessory', 'Style or accessory'], ['rendering_defect', 'Rendering or animation defect'],
] as const

export type FighterReviewProps = {
  response: CaptureResponse
  onFeedback: (captureId:string, input:FeedbackInput) => Promise<unknown>
  onCorrect: (captureId:string, input:CorrectionInput) => Promise<CaptureResponse>
  onRevised: (response:CaptureResponse) => void
  onConfirm: () => Promise<void>
  onRetake: () => void
  onCrop?: () => void
  onBusy?: (busy:boolean) => void
}

/** Current player's proposal only. Nothing is cached across the private handoff. */
export default function FighterReview({response,onFeedback,onCorrect,onRevised,onConfirm,onRetake,onCrop,onBusy}:FighterReviewProps) {
  const fighter = response.fighter!
  const [recognition,setRecognition] = useState<'correct'|'corrected'|'unsure'|null>(null)
  const [creative,setCreative] = useState<'keep'|'change'|'skipped'>('skipped')
  const [label,setLabel] = useState('')
  const [reasons,setReasons] = useState<string[]>([])
  const [comment,setComment] = useState('')
  const [sharedConsent,setSharedConsent] = useState(false)
  const [working,setWorking] = useState<'save'|'correct'|'confirm'|null>(null)
  const [failure,setFailure] = useState('')
  const [feedbackFailure,setFeedbackFailure] = useState(false)
  const [saved,setSaved] = useState(false)
  const lock = useRef(false)
  const keys = useRef(new Map<string,string>())
  const outputId = response.output_id ?? fighter.output_id
  const version = response.pipeline_version_id ?? fighter.pipeline_version_id
  const available = !!outputId && !!version && version !== 'legacy-unknown'
  const canConfirm = !available || recognition === 'correct'
  const scope = response.saved_resident_preview ? 'Battle preview · saved island resident is kept' : 'Proposed island appearance'
  const previewFighter = {image_ref:String(fighter.image_ref ?? response.image_url), display_name:String(fighter.display_name), object_type:String(fighter.object_type), visual_spec: fighter.visual_spec as WorldCharacter['visual_spec']}
  const keyFor = (scope:string,payload:object) => {
    const signature=scope+JSON.stringify(payload)
    if(!keys.current.has(signature))keys.current.set(signature,crypto.randomUUID())
    return keys.current.get(signature)!
  }
  const dirty = () => {setSaved(false);setFailure('');setFeedbackFailure(false)}
  const save = async () => {
    if(!available || !recognition)return
    const payload = {output_id:outputId,pipeline_version_id:version,recognition_verdict:recognition,creative_verdict:creative,correction_label:recognition==='corrected'?label.trim():undefined,reasons:creative==='change'?reasons:[],comment:comment.trim()||undefined,shared_consent:sharedConsent}
    await onFeedback(response.capture_id,{...payload,idempotency_key:keyFor('feedback',payload)})
    setSaved(true)
  }
  const run = async (kind:'save'|'correct'|'confirm',action:()=>Promise<void>) => {
    if(lock.current)return
    lock.current=true;setWorking(kind);onBusy?.(true);setFailure('');setFeedbackFailure(false)
    try{await action()}catch(error){setFailure(error instanceof Error?error.message:'This change could not be saved. Please retry.')}finally{lock.current=false;setWorking(null);onBusy?.(false)}
  }
  const correct = (kind:'factual'|'style') => run('correct',async()=>{
    try{await save()}catch(error){setFeedbackFailure(true);throw error}
    const payload = {output_id:outputId!,pipeline_version_id:version!,kind,canonical_label:kind==='factual'?label.trim():undefined,details:comment.trim()||undefined,reasons:kind==='style'?reasons:[]}
    const revised=await onCorrect(response.capture_id,{...payload,idempotency_key:keyFor('correction',payload)})
    onRevised(revised)
  })
  const confirm = (withoutFeedback=false) => run('confirm',async()=>{
    if(!withoutFeedback){try{await save()}catch(error){setFeedbackFailure(true);throw error}}
    await onConfirm()
  })

  return <section className="fighter-review" aria-label="Review your fighter">
    <div className="review-topline"><span className="review-label">YOUR OBJECT, YOUR CALL</span><span className="review-class">{fighter.archetype} <i/> 100 HP</span></div>
    <div className="review-intro"><div><h2>{fighter.display_name}</h2><p>We see <strong>{response.observed_object?.label??fighter.observed_object?.label??fighter.object_type}</strong>. You decide if we got it right.</p></div><span className="review-output" title={outputId??'Historical output'}>{outputId?`PROPOSAL ${outputId.slice(0,7)}`:'RECOVERED FIGHTER'}</span></div>
    {response.evidence?.identity_support?.detail&&<p className="review-notice"><strong>YOLO + Gemini cross-check: </strong>{response.evidence.identity_support.detail}</p>}
    <div className="review-visuals">
      <figure className="review-source"><img src={response.image_url} alt={`Source photograph for ${fighter.object_type}`}/><figcaption><span>01</span> YOUR PHOTOGRAPH</figcaption></figure>
      <div className="review-model"><Suspense fallback={<div className="review-preview-loading">Opening the 3D preview…</div>}><CharacterPreview fighter={previewFighter} scope={scope} compact/></Suspense></div>
    </div>
    {response.saved_resident_preview && <details className="review-resident"><summary>This object already lives on your island <span>View saved appearance</span></summary><p>The preview above is for this battle. Your resident’s original appearance and home stay the same.</p><Suspense fallback={<p>Opening saved resident…</p>}><CharacterPreview fighter={response.saved_resident_preview} scope="Saved island resident · unchanged" compact/></Suspense></details>}
    {available ? <div className="review-decisions">
      <fieldset disabled={!!working}><legend><span>01</span> Did we identify your object correctly?</legend><div className="review-choice-row">
        <button type="button" aria-pressed={recognition==='correct'} className={recognition==='correct'?'selected':''} onClick={()=>{dirty();setRecognition('correct')}}><Check size={16}/> Correct</button>
        <button type="button" aria-pressed={recognition==='corrected'} className={recognition==='corrected'?'selected':''} onClick={()=>{dirty();setRecognition('corrected')}}><RefreshCw size={15}/> Correct it</button>
        <button type="button" aria-pressed={recognition==='unsure'} className={recognition==='unsure'?'selected':''} onClick={()=>{dirty();setRecognition('unsure')}}><HelpCircle size={16}/> Not sure</button>
      </div>
      {recognition==='corrected' && <div className="review-correction"><label>What is the object?<input maxLength={80} value={label} onChange={e=>{dirty();setLabel(e.target.value)}} placeholder="A short object name, e.g. watering can"/></label><button type="button" className="review-secondary" disabled={!label.trim()} onClick={()=>void correct('factual')}>Check this correction <ArrowRight size={15}/></button><p>We’ll check the same photograph again. The original proposal stays in its history.</p></div>}
      {recognition==='unsure' && <div className="review-uncertain"><p>Let’s give the object another look. Select a clearer region or take a fresh photo.</p><div>{onCrop&&<button type="button" className="review-secondary" onClick={()=>void run('save',async()=>{try{await save()}catch{setFeedbackFailure(true);throw new Error('Feedback was not saved. Retry, or use Retake below without saving.')}onCrop()})}>Select or crop</button>}<button type="button" className="review-secondary" onClick={()=>void run('save',async()=>{try{await save()}catch{setFeedbackFailure(true);throw new Error('Feedback was not saved. Retry, or use Retake below without saving.')}onRetake()})}>Use another photograph</button></div></div>}
      </fieldset>
      <fieldset disabled={!!working}><legend><span>02</span> Keep this fighter? <small>Optional</small></legend><div className="review-choice-row"><button type="button" aria-pressed={creative==='keep'} className={creative==='keep'?'selected':''} onClick={()=>{dirty();setCreative(creative==='keep'?'skipped':'keep')}}><CheckCircle2 size={16}/> Keep</button><button type="button" aria-pressed={creative==='change'} className={creative==='change'?'selected':''} onClick={()=>{dirty();setCreative(creative==='change'?'skipped':'change')}}><SlidersHorizontal size={16}/> Change details</button></div>
      {creative==='change' && <div className="review-correction"><div className="review-reasons">{REASONS.map(([id,text])=><label key={id}><input type="checkbox" checked={reasons.includes(id)} onChange={()=>{dirty();setReasons(old=>old.includes(id)?old.filter(reason=>reason!==id):[...old,id])}}/>{text}</label>)}</div><label>A little direction <small>Optional</small><textarea value={comment} maxLength={400} rows={2} placeholder="Keep the blue colour; try a smaller hat…" onChange={e=>{dirty();setComment(e.target.value)}}/></label><button type="button" className="review-secondary" disabled={recognition!=='correct'||(!reasons.length&&!comment.trim())} onClick={()=>void correct('style')}>Try these details <ArrowRight size={15}/></button><p>Appearance and name only. Combat class, stats and saved residents stay fixed.</p></div>}
      </fieldset>
    </div> : <p className="review-notice">Historical proposal: its feedback version is unavailable. You can use this fighter, or retake the photo for a new reviewed proposal.</p>}
    {available&&<label className="review-consent"><input type="checkbox" disabled={!!working} checked={sharedConsent} onChange={e=>{dirty();setSharedConsent(e.target.checked)}}/><span>Allow this object photo and feedback for reviewed evaluation and reference use.<small>Optional. The creator must review it first. Leaving this off does not affect your game.</small></span></label>}
    {failure&&<div className="review-error" role="alert"><b>{feedbackFailure?'Feedback has not been saved.':'Could not finish that action.'}</b><p>{failure}</p>{feedbackFailure&&canConfirm&&<button type="button" disabled={!!working} onClick={()=>void confirm(true)}>Continue without saving feedback</button>}</div>}
    <div className="review-footer"><div aria-live="polite">{working?<span className="review-saving">{working==='correct'?'Preparing the revised fighter…':working==='confirm'?'Saving and locking your fighter…':'Saving your review…'}</span>:saved?<span className="review-saved"><Check size={14}/> Feedback saved for this proposal.</span>:<span>{sharedConsent?'You opted in to reviewed evaluation and reference use.':'Feedback stays with this round. Shared evaluation is off.'}</span>}</div><button type="button" className="review-confirm" disabled={!!working||!canConfirm} onClick={()=>void confirm()}>Lock in my fighter <ArrowRight size={18}/></button></div>
  </section>
}
