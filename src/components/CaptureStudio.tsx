import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent, ReactNode } from 'react'
import { Camera, Check, Crop, ImageUp, RotateCcw, ScanLine, X } from 'lucide-react'
import { cameraFailureMessage, captureVideoFrame, clampImageCrop, normalizeImage } from '../lib/imageInput'
import type { ImageCrop, NormalizedImage } from '../lib/imageInput'
import { LEGACY_THEME, type RoundTheme, type ThemeValidation, type FeedbackInput, type CorrectionInput, type CaptureProgress, type CaptureProgressListener } from '../lib/api'
import type { WorldCharacter } from './WorldView'
import FighterReview from './FighterReview'
import './SketchCanvas.css'
import './CaptureStudio.css'

export type CaptureResponse = {
  theme_validation?: ThemeValidation | null
  capture_id: string
  output_id?: string
  pipeline_version_id?: string
  observed_object?: {canonical_type_id:string;label:string;visible_features?:string[]}
  saved_resident_preview?: Pick<WorldCharacter, 'visual_spec'|'image_ref'|'display_name'|'object_type'> | null
  status: 'recognized' | 'needs_selection' | 'needs_recapture'
  image_url: string
  width: number
  height: number
  detections?: { id: string; label: string; box: ImageCrop; score?: number }[]
  fighter?: Record<string, any>
  evidence?: Record<string, any>
  message?: string
  trace?: any[]
  degraded?: boolean
}

export type CaptureInput = { captureId: string; file: File; source: 'camera' | 'upload'; crop?: ImageCrop }
export type CaptureStudioProps = {
  theme?: RoundTheme | null
  player: 1 | 2
  duration: number
  onPrepare: (input: CaptureInput, signal: AbortSignal, onProgress?: CaptureProgressListener) => Promise<CaptureResponse>
  onConfirm: (fighter: any) => void | Promise<void>
  onCancel: () => void
  initialResponse?: CaptureResponse | null
  onFeedback: (captureId:string, input:FeedbackInput) => Promise<unknown>
  onCorrect: (captureId:string, input:CorrectionInput) => Promise<CaptureResponse>
}

type Stage = 'handoff' | 'idle' | 'permission' | 'camera' | 'normalizing' | 'processing' | 'selection' | 'recognized' | 'recapture' | 'error'
type PreparedCapture = NormalizedImage & { captureId: string; source: 'camera' | 'upload'; crop?: ImageCrop }
type Point = { x: number; y: number }

function ToolbarButton({ children, label, disabled, selected, onClick }: { children: ReactNode; label: string; disabled?: boolean; selected?: boolean; onClick: () => void }) {
  return <button type="button" className={`sketch-tool capture-tool ${selected ? 'is-selected' : ''}`} disabled={disabled} aria-label={label} aria-pressed={selected} onClick={onClick}>{children}<span>{label}</span></button>
}

const captureStageTitles: Record<string, string> = {
  registered: 'PHOTO RECEIVED', local_detection: 'FINDING OBJECTS LOCALLY', local_ocr: 'READING VISIBLE TEXT LOCALLY',
  queued: 'WAITING FOR GEMINI', gemini_recognition: 'GEMINI IS READING YOUR OBJECT', validation: 'CHECKING THE FIGHTER',
  repair: 'REFINING THE PROPOSAL', saving: 'SAVING YOUR FIGHTER', complete: 'PREPARATION SAVED', failed: 'PREPARATION STOPPED',
}

export function CaptureProgressPanel({ normalizing, progress, unavailable, seconds }: { normalizing: boolean; progress: CaptureProgress | null; unavailable: boolean; seconds: number }) {
  const queued = !unavailable && progress?.stage === 'queued'
  const wait = progress?.queue?.dispatch_wait_seconds
  const waitReason = progress?.queue?.wait_reason
  return <div className="capture-processing" role="status">
    <span className="capture-loading-mark" aria-hidden="true">✳</span>
    <strong>{normalizing ? 'DEVELOPING YOUR PHOTO…' : unavailable ? 'PROGRESS UNAVAILABLE' : progress ? captureStageTitles[progress.stage] || 'PREPARING YOUR FIGHTER' : 'SENDING YOUR PHOTOGRAPH…'}</strong>
    <span>{normalizing ? 'Making a clean, correctly oriented image.' : unavailable ? 'The original request is still pending. Your photograph is kept for recovery.' : progress?.message || 'Waiting for the backend to register this capture. No preparation stage has been reported yet.'}</span>
    {queued && typeof wait === 'number' && wait > 0 && <small>Next admission check in about {Math.ceil(wait)} seconds. This is not a completion estimate.</small>}
    {queued && <small>{waitReason === 'provider_cooldown' ? 'Gemini is cooling down after a provider error.' : waitReason === 'local_concurrency' ? 'Other normal Gemini requests are running. Your photograph is waiting for a free slot.' : 'Camera checks run independently of the island pace.'}</small>}
    {!normalizing && progress?.model && !unavailable && <small>Model: {progress.model}{progress.attempt && progress.attempt > 1 ? ` · attempt ${progress.attempt}` : ''}</small>}
    <small>Your capture timer is paused.</small>
    {!normalizing && <small>Elapsed {Math.floor(seconds / 60)}m {String(seconds % 60).padStart(2, '0')}s · this photograph is kept for recovery.</small>}
  </div>
}

function EvidenceDetails({ response }: { response: CaptureResponse }) {
  const evidence = response.evidence ?? {}
  const support = evidence.identity_support
  return <details className="capture-evidence">
    <summary>How this fighter was prepared{response.degraded ? ' · limited evidence' : ''}</summary>
    <p>Local YOLO finds supported object classes. Local OCR reads printed text. Gemini interprets the selected photograph with that evidence. Their scores are not interchangeable measures of certainty.</p>
    {support?.detail && <p><strong>Identity cross-check:</strong> {support.detail}</p>}
    {(['detector','ocr'] as const).map(name=>evidence[name]?.detail&&<p key={name}><strong>{name==='detector'?'YOLO':'OCR'}:</strong> {evidence[name].detail}</p>)}
    <dl>{Object.entries(evidence).map(([name, value]) => <div key={name}><dt>{name.replaceAll('_', ' ')}</dt><dd>{typeof value === 'object' && value !== null ? String(value.status ?? 'reported') : String(value)}</dd></div>)}</dl>
    {response.detections?.length ? <p>Detected candidates: {response.detections.map(item => `${item.label}${typeof item.score === 'number' ? ` (detector score ${item.score.toFixed(2)})` : ''}`).join(', ')}.</p> : null}
    {response.trace?.length ? <ol>{response.trace.map((item, index) => <li key={index}>{typeof item === 'string' ? item : `${item.tool ?? item.name ?? item.stage ?? 'Check'}: ${item.status ?? (item.valid === true || item.ok === true ? 'passed' : item.valid === false || item.ok === false ? 'failed' : item.result?.ok === true ? 'passed' : 'reported')}${item.duration_ms != null ? ` (${item.duration_ms} ms)` : ''}`}</li>)}</ol> : null}
    {Array.isArray(evidence.related_discoveries) && evidence.related_discoveries.length > 0 && <section aria-label="Related discoveries"><h3>Related discoveries</h3><p>Similar approved types from Atlas Vector Search. Similarity does not mean identity or ownership.</p><ul>{evidence.related_discoveries.map((item:any,index:number)=><li key={item.canonical_key??index}>{item.display_name??item.label??item.canonical_key??item.canonical_type_id} {typeof item.score==='number'?`· similarity ${item.score.toFixed(2)}`:''}</li>)}</ul></section>}
    <pre aria-label="Recognition evidence details">{JSON.stringify(evidence, null, 2).slice(0, 6000)}</pre>
    <p>Your photograph becomes a framed fighter. Character personality and battle abilities are fictional; this is not a 3D scan.</p>
  </details>
}

export function CaptureStudio({ player, duration, onPrepare, onConfirm, onCancel, initialResponse, onFeedback, onCorrect, theme: savedTheme }: CaptureStudioProps) {
  const theme = savedTheme ?? LEGACY_THEME
  const [stage, setStage] = useState<Stage>('handoff')
  const [remaining, setRemaining] = useState(duration)
  const [processingSeconds, setProcessingSeconds] = useState(0)
  const [progress, setProgress] = useState<CaptureProgress | null>(null)
  const [progressUnavailable, setProgressUnavailable] = useState(false)
  const remainingMs = useRef(duration * 1000)
  const [response, setResponse] = useState<CaptureResponse | null>(null)
  const [preview, setPreview] = useState('')
  const [message, setMessage] = useState('')
  const [frameReady, setFrameReady] = useState(false)
  const [cropMode, setCropMode] = useState(false)
  const [crop, setCrop] = useState<ImageCrop | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [surfaceSize, setSurfaceSize] = useState({ width: 800, height: 496 })
  const videoRef = useRef<HTMLVideoElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const surfaceRef = useRef<HTMLDivElement>(null)
  const coordinateRef = useRef<HTMLDivElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const originalRef = useRef<PreparedCapture | null>(null)
  const captureRef = useRef<PreparedCapture | null>(null)
  const urlRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const generation = useRef(0)
  const mounted = useRef(true)
  const submitted = useRef(false)
  const dragRef = useRef<{ pointerId: number; start: Point } | null>(null)

  useEffect(() => {
    if(stage!=='processing'){setProcessingSeconds(0);return}
    const began=Date.now()
    const interval=window.setInterval(()=>setProcessingSeconds(Math.floor((Date.now()-began)/1000)),1000)
    return()=>window.clearInterval(interval)
  },[stage])

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach(track => track.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  const invalidate = useCallback(() => {
    generation.current += 1
    abortRef.current?.abort()
    abortRef.current = null
    stopCamera()
    return generation.current
  }, [stopCamera])

  const discard = useCallback(() => {
    invalidate()
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = null
    originalRef.current = null
    captureRef.current = null
    submitted.current = false
    dragRef.current = null
    setPreview('')
    setResponse(null)
    setProgress(null)
    setProgressUnavailable(false)
    setMessage('')
    setFrameReady(false)
    setCrop(null)
    setCropMode(false)
    setConfirming(false)
  }, [invalidate])

  useLayoutEffect(() => {
    mounted.current = true
    discard()
    remainingMs.current = Math.max(1, duration) * 1000
    setRemaining(Math.max(1, duration))
    setStage('handoff')
    return () => {
      mounted.current = false
      invalidate()
      if (urlRef.current) URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
  }, [player, duration, discard, invalidate])

  useEffect(() => {
    const element = surfaceRef.current
    if (!element) return
    const observer = new ResizeObserver(() => setSurfaceSize({ width: element.clientWidth, height: element.clientHeight }))
    observer.observe(element)
    setSurfaceSize({ width: element.clientWidth, height: element.clientHeight })
    return () => observer.disconnect()
  }, [])

  // Time runs only while framing or selecting. Permission and recognition never consume it.
  useEffect(() => {
    const active = stage === 'camera' && frameReady || ['selection', 'recognized', 'recapture'].includes(stage)
    if (!active || confirming) return
    let previous = performance.now()
    const interval = window.setInterval(() => {
      const now = performance.now()
      if (!document.hidden) remainingMs.current = Math.max(0, remainingMs.current - (now - previous))
      previous = now
      setRemaining(Math.ceil(remainingMs.current / 1000))
    }, 100)
    return () => window.clearInterval(interval)
  }, [stage, frameReady, confirming])

  useEffect(() => {
    if (stage !== 'camera' || !streamRef.current || !videoRef.current) return
    const video = videoRef.current
    const request = generation.current
    video.srcObject = streamRef.current
    video.play().catch(() => {
      if (!mounted.current || generation.current !== request) return
      setMessage('The camera preview could not play. Try the camera again, or upload a photo.')
      stopCamera()
      setStage('idle')
    })
  }, [stage, stopCamera])

  const isCurrent = (request: number) => mounted.current && generation.current === request

  const prepare = async (capture: PreparedCapture) => {
    const request = invalidate()
    const controller = new AbortController()
    abortRef.current = controller
    captureRef.current = capture
    setResponse(null)
    setCropMode(false)
    setProgress(null)
    setProgressUnavailable(false)
    setProcessingSeconds(0)
    setMessage('Sending your photograph. Waiting for the backend to register this capture…')
    setStage('processing')
    try {
      const result = await onPrepare({ captureId: capture.captureId, file: capture.file, source: capture.source, crop: capture.crop }, controller.signal, next => {
        if (!isCurrent(request) || controller.signal.aborted) return
        if (next && next.capture_id !== capture.captureId) return
        setProgress(next)
        setProgressUnavailable(!next)
        setMessage(next?.message || 'Preparation progress is unavailable. The original capture request is still pending; your photograph is kept for recovery.')
      })
      if (!isCurrent(request) || controller.signal.aborted) return
      if (result.capture_id !== capture.captureId) throw new Error('The returned capture did not match this photograph. Please retry.')
      if (result.status === 'recognized' && !result.fighter) throw new Error('The photograph was recognised, but its fighter was not ready. Please retry.')
      setResponse(result)
      if (result.status === 'recognized') {
        setStage('recognized')
        setMessage(result.degraded ? 'Ready to battle. Some supporting evidence was unavailable; open the details to see which.' : 'Object recognised. Fighter checked. Ready to battle.')
      } else if (result.status === 'needs_selection') {
        setStage('selection')
        setMessage(result.message || 'Choose one outlined object, or crop tightly around your fighter.')
      } else {
        setStage('recapture')
        setMessage(result.message || 'We need a clearer view. Crop around one object, retake, or choose another photograph.')
      }
    } catch (error) {
      if (!isCurrent(request) || controller.signal.aborted) return
      setStage('error')
      setMessage(error instanceof Error ? error.message : 'The fighter could not be prepared. Retry or choose another photograph.')
    } finally {
      if (isCurrent(request)) abortRef.current = null
    }
  }

  const acceptImage = (image: NormalizedImage, source: 'camera' | 'upload') => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = URL.createObjectURL(image.file)
    const capture: PreparedCapture = { ...image, source, captureId: crypto.randomUUID() }
    originalRef.current = capture
    captureRef.current = capture
    setPreview(urlRef.current)
    setCrop(null)
    void prepare(capture)
  }

  const startCamera = async () => {
    discard()
    const request = generation.current
    setStage('permission')
    setMessage('Allow camera access in your browser. Your timer is paused.')
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera unavailable')
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 960 }, facingMode: 'environment' }, audio: false })
      if (!isCurrent(request)) { stream.getTracks().forEach(track => track.stop()); return }
      streamRef.current = stream
      setMessage('Put one object in the frame. Your photograph will not be mirrored.')
      setStage('camera')
    } catch (error) {
      if (!isCurrent(request)) return
      setStage('idle')
      setMessage(cameraFailureMessage(error))
    }
  }

  const captureCamera = async () => {
    const video = videoRef.current
    if (!video || !frameReady || stage !== 'camera') return
    const request = generation.current
    setStage('normalizing')
    setMessage('Preparing your photograph…')
    try {
      const image = await captureVideoFrame(video)
      stopCamera()
      if (isCurrent(request)) acceptImage(image, 'camera')
    } catch (error) {
      if (!isCurrent(request)) return
      stopCamera()
      setStage('idle')
      setMessage(error instanceof Error ? error.message : 'Capture failed. Please try again.')
    }
  }

  const upload = async (file?: File) => {
    if (!file) return
    discard()
    const request = generation.current
    const controller = new AbortController()
    abortRef.current = controller
    setStage('normalizing')
    setMessage('Preparing your photograph…')
    try {
      const image = await normalizeImage(file, controller.signal)
      if (isCurrent(request)) acceptImage(image, 'upload')
    } catch (error) {
      if (!isCurrent(request) || controller.signal.aborted) return
      setStage('idle')
      setMessage(error instanceof Error ? error.message : 'The image could not be opened. Choose a different photograph.')
    }
  }

  const selectCrop = (nextCrop: ImageCrop) => {
    const original = originalRef.current
    if (!original) return
    const bounded = clampImageCrop(nextCrop, original.width, original.height)
    if (!bounded) { setMessage('Make the crop at least 16 pixels wide and high.'); return }
    setCrop(bounded)
    // A selected region is new evidence, never a mutation of a previously accepted capture.
    void prepare({ ...original, captureId: crypto.randomUUID(), crop: bounded })
  }

  const startCropping = () => {
    const original = originalRef.current
    if (!original) return
    invalidate()
    setResponse(null)
    setStage('selection')
    setCropMode(true)
    setCrop({ x: Math.round(original.width * 0.1), y: Math.round(original.height * 0.1), width: Math.round(original.width * 0.8), height: Math.round(original.height * 0.8) })
    setMessage('Drag a box around one object, or adjust the crop fields. Then use this crop.')
  }

  const cropPoint = (event: { clientX: number; clientY: number }): Point | null => {
    const rect = coordinateRef.current?.getBoundingClientRect()
    const original = originalRef.current
    if (!rect || !original || !rect.width || !rect.height) return null
    return { x: Math.max(0, Math.min(original.width, (event.clientX - rect.left) / rect.width * original.width)), y: Math.max(0, Math.min(original.height, (event.clientY - rect.top) / rect.height * original.height)) }
  }
  const cropPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!cropMode || event.button !== 0) return
    const point = cropPoint(event)
    if (!point) return
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    dragRef.current = { pointerId: event.pointerId, start: point }
    setCrop({ x: Math.round(point.x), y: Math.round(point.y), width: 0, height: 0 })
  }
  const cropPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!cropMode || !drag || drag.pointerId !== event.pointerId) return
    const point = cropPoint(event)
    if (!point) return
    setCrop({ x: Math.round(Math.min(point.x, drag.start.x)), y: Math.round(Math.min(point.y, drag.start.y)), width: Math.round(Math.abs(point.x - drag.start.x)), height: Math.round(Math.abs(point.y - drag.start.y)) })
  }
  const cropPointerEnd = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return
    dragRef.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
  }

  const confirm = async () => {
    if (stage !== 'recognized' || !response?.fighter || submitted.current || cropMode) return
    submitted.current = true
    setConfirming(true)
    stopCamera()
    const request = generation.current
    try { await onConfirm(response.fighter) }
    catch (error) {
      if (!isCurrent(request)) return
      submitted.current = false
      setConfirming(false)
      setMessage(error instanceof Error ? error.message : 'Could not confirm this fighter. Try again.')
    }
  }

  const original = originalRef.current
  const selectedImage = stage === 'recognized' && response?.image_url && !cropMode ? response.image_url : preview
  const selectedDimensions = stage === 'recognized' && response?.image_url && !cropMode ? { width: response.width, height: response.height } : original
  const aspect = selectedDimensions?.width && selectedDimensions.height ? selectedDimensions.width / selectedDimensions.height : 1
  const imageWidth = Math.min(surfaceSize.width, surfaceSize.height * aspect)
  const imageHeight = imageWidth / aspect
  const busy = stage === 'normalizing' || stage === 'processing'
  const started = stage !== 'handoff'
  const canCrop = !!original && !busy && !confirming
  const detections = stage === 'selection' && !cropMode ? response?.detections ?? [] : []
  const displayBox = (box: ImageCrop) => ({ left: `${100 * box.x / (original?.width || 1)}%`, top: `${100 * box.y / (original?.height || 1)}%`, width: `${100 * box.width / (original?.width || 1)}%`, height: `${100 * box.height / (original?.height || 1)}%` })

  return <section className={`sketch-screen sketch-player-${player} capture-screen ${stage === 'recognized' ? 'capture-reviewing' : ''}`} aria-label={`Player ${player} capture studio`}>
    <div className="sketch-heading">
      <div className="sketch-heading-copy">
        <span className="sketch-eyebrow"><span /> PLAYER {player} / {stage === 'recognized' ? 'THE REVIEW' : 'CAPTURE STUDIO'}</span>
        <h1>{stage === 'recognized' ? <>A LITTLE MORE <em>YOU.</em></> : <>FIND YOUR <em>CHAMPION.</em></>}</h1>
        <p>{stage === 'recognized' ? 'A real subject. A fictional fighter. Check its identity and round eligibility.' : theme.instructions}</p>
      </div>
      <div className={`sketch-clock ${remaining <= 10 && started ? 'sketch-clock-urgent' : ''}`} aria-label={`${remaining} seconds of active capture time remaining`} title="Paused while permission or recognition is pending. Nothing submits automatically.">
        <Camera size={20} aria-hidden="true" /><span>{String(remaining).padStart(2, '0')}<small>s</small></span>
        <div className="sketch-clock-track"><div style={{ transform: `scaleX(${remaining / Math.max(1, duration)})` }} /></div>
      </div>
    </div>

    <div className="sketch-workspace">
      <div className="sketch-side-note" aria-hidden="true">one object.<br />big attitude.<svg viewBox="0 0 85 60"><path d="M6 7Q15 45 63 34M51 20l14 15-20 8" /></svg></div>
      <div className="sketch-notebook">
        <div className="sketch-binding" aria-hidden="true">{Array.from({ length: 9 }, (_, index) => <i key={index} />)}</div>
        <div className="sketch-paper-top"><span className="sketch-player-badge"><b>P{player}</b> YOUR TURN</span><span className="sketch-theme">THEME <strong>{theme.name.toUpperCase()}</strong><ScanLine size={19} aria-hidden="true" /></span></div>
        <div ref={surfaceRef} className={`sketch-canvas-surface capture-surface ${!started ? 'is-ready' : ''}`}>
          {(stage === 'camera' || stage === 'permission') && <video ref={videoRef} className="capture-video" muted playsInline autoPlay aria-label="Camera preview, not mirrored" onLoadedData={() => setFrameReady(!!videoRef.current?.videoWidth && (videoRef.current?.readyState ?? 0) >= 2)} onCanPlay={() => setFrameReady(!!videoRef.current?.videoWidth && (videoRef.current?.readyState ?? 0) >= 2)} />}
          {stage === 'camera' && <div className="capture-framing-guide" aria-hidden="true"><span>ONE OBJECT. CENTRE STAGE.</span></div>}
          {selectedImage && stage !== 'camera' && stage !== 'permission' && <div ref={coordinateRef} className={`capture-coordinate-frame ${cropMode ? 'is-cropping' : ''}`} style={{ width: imageWidth, height: imageHeight }} onPointerDown={cropPointerDown} onPointerMove={cropPointerMove} onPointerUp={cropPointerEnd} onPointerCancel={cropPointerEnd} onLostPointerCapture={cropPointerEnd}>
            <img src={selectedImage} alt={stage === 'recognized' ? 'Your accepted fighter photograph' : 'Your photograph before selecting one object'} draggable="false" />
            {detections.map((item, index) => {
              const box = original && clampImageCrop(item.box, original.width, original.height)
              return box ? <button key={item.id} className="capture-detection" style={displayBox(box)} type="button" aria-label={`Select ${item.label}, object ${index + 1}`} onClick={() => selectCrop(box)}><span>{index + 1}. {item.label}</span></button> : null
            })}
            {cropMode && crop && <div className="capture-crop-outline" style={displayBox(crop)} aria-hidden="true"><span>YOUR FIGHTER</span></div>}
          </div>}
          {stage === 'idle' && !preview && <div className="capture-empty"><Camera size={48} strokeWidth={1.2} aria-hidden="true" /><h2>{theme.name.toUpperCase()}</h2><p>Try {theme.examples.join(', ')}. One clear subject in the spotlight.</p><button type="button" className="sketch-start-button" onClick={() => void startCamera()}>OPEN CAMERA <span aria-hidden="true">↗</span></button><button className="capture-text-button" onClick={() => inputRef.current?.click()}>or upload a photograph</button></div>}
          {stage === 'permission' && <div className="capture-processing"><Camera size={32} /><strong>CAMERA PERMISSION</strong><span>Choose Allow in your browser. Your timer is paused.</span><button type="button" className="capture-text-button" onClick={() => { discard(); setStage('idle'); inputRef.current?.click() }}>Use an uploaded photo instead</button></div>}
          {busy && <CaptureProgressPanel normalizing={stage === 'normalizing'} progress={progress} unavailable={progressUnavailable} seconds={processingSeconds} />}
          {stage === 'recognized' && <span className="capture-ready-seal"><Check size={16} /> {response?.theme_validation&&response.theme_validation.verdict!=='eligible'?'CHECK THE ROUND THEME':'READY FOR REVIEW'}</span>}
          {stage === 'handoff' && <div className="sketch-ready-overlay"><span className="sketch-ready-kicker">{player === 2 ? 'A LITTLE MYSTERY MAKES A GOOD FIGHT' : 'YOUR EVERYDAY. THEIR PROBLEM.'}</span><div className="sketch-ready-sticker">P{player}</div><h2>{player === 2 ? 'PASS THE SKETCHBOOK.' : 'CAMERAS AT THE READY.'}</h2><p>{player === 2 ? 'Player 1, look away. Player 2, choose your secret weapon.' : theme.instructions}</p><button type="button" className="sketch-start-button" onClick={() => { if(initialResponse){setResponse(initialResponse);setPreview(initialResponse.image_url);setStage('recognized');setMessage('Your fighter was recovered. Review it before continuing.')}else setStage('idle') }}>I'M READY <span aria-hidden="true">↗</span></button><small>{theme.examples.join(' · ')}<br/>Your timer runs only while framing or selecting.</small></div>}
        </div>
        <div className="sketch-paper-bottom"><span>ORIGINAL PHOTO. UNLIMITED ATTITUDE.</span><span>CAPTURE No. 00{player}</span></div>
      </div>
      <span className="sketch-star-doodle" aria-hidden="true">✳</span>
    </div>

    {stage === 'recognized' && response?.fighter && <FighterReview key={response.output_id ?? response.fighter.output_id ?? response.capture_id} response={response} onFeedback={onFeedback} onCorrect={onCorrect} onRevised={revised=>{setResponse(revised);setStage(revised.status==='recognized'?'recognized':revised.status==='needs_selection'?'selection':'recapture');setMessage(revised.message??'Revised proposal ready. Review the new result before locking it in.')}} onConfirm={confirm} onBusy={setConfirming} onRetake={()=>{discard();setStage('idle')}} onCrop={originalRef.current?startCropping:undefined}/> }

    <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" className="capture-file-input" aria-label="Upload a fighter photograph" tabIndex={-1} onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; void upload(file) }} />
    <div className="sketch-bottom-bar">
      <div className="sketch-toolbar capture-toolbar" role="toolbar" aria-label="Capture tools">
        <ToolbarButton label="Camera" disabled={!started || busy || confirming || stage === 'permission'} selected={stage === 'camera'} onClick={() => void startCamera()}><Camera size={19} /></ToolbarButton>
        <ToolbarButton label="Upload" disabled={!started || busy || confirming} onClick={() => inputRef.current?.click()}><ImageUp size={19} /></ToolbarButton>
        <span className="sketch-toolbar-rule" />
        <ToolbarButton label="Capture" disabled={stage !== 'camera' || !frameReady} onClick={() => void captureCamera()}><ScanLine size={19} /></ToolbarButton>
        <ToolbarButton label="Retake" disabled={!started || stage === 'idle' || confirming} onClick={() => { discard(); setStage('idle') }}><RotateCcw size={18} /></ToolbarButton>
        <ToolbarButton label="Crop" disabled={!canCrop} selected={cropMode} onClick={startCropping}><Crop size={18} /></ToolbarButton>
      </div>
      {stage !== 'recognized' && <span className="capture-next-step">{busy ? 'Preparing your fighter…' : 'Capture → review → clash'}</span>}
    </div>

    {cropMode && crop && original && <div className="capture-crop-tools">
      <span>Crop in photo pixels</span>
      {(['x', 'y', 'width', 'height'] as const).map(key => <label key={key}>{key}<input type="number" min={key === 'x' || key === 'y' ? 0 : 16} max={key === 'x' || key === 'width' ? original.width : original.height} step={1} value={crop[key]} onChange={event => setCrop({ ...crop, [key]: Number(event.target.value) })} /></label>)}
      <button type="button" className="capture-crop-apply" onClick={() => selectCrop(crop)}><Check size={16} /> USE THIS CROP</button>
      <button type="button" className="capture-text-button" onClick={() => { setCropMode(false); setCrop(null); void prepare({ ...original, captureId: crypto.randomUUID() }) }}><X size={15} /> Whole photo</button>
    </div>}
    {stage === 'selection' && !cropMode && detections.length > 0 && <div className="capture-selection-list" aria-label="Choose one detected object">{detections.map((item, index) => <button key={item.id} type="button" onClick={() => selectCrop(item.box)}>{index + 1}. {item.label} <span aria-hidden="true">↗</span></button>)}</div>}
    {stage === 'error' && captureRef.current && <button type="button" className="capture-retry" onClick={() => captureRef.current && void prepare(captureRef.current)}><RotateCcw size={16} /> Retry this photograph</button>}
    <div className="sketch-footnote"><button type="button" disabled={confirming} onClick={() => { discard(); onCancel() }}>← Back to lobby</button><span role="status" aria-live="polite">{message || (remaining === 0 ? 'Time is up. Nothing submits automatically; finish choosing your photograph when ready.' : 'One object becomes one fighter. Confirm it before passing the laptop.')}</span><span className="sketch-counter">{player} / 2 FIGHTERS</span></div>
    {response && <EvidenceDetails response={response} />}
  </section>
}

export default CaptureStudio
