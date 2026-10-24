import { characterDisplayScale } from './objectPresentation'
import { Component, useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { AmbientLight, Box3, Color, DirectionalLight, Group, Mesh, PerspectiveCamera, Scene, Vector3, WebGLRenderTarget } from 'three'
import { Camera, Check, CircleAlert, RotateCw } from 'lucide-react'
import { animateCharacterBody, CharacterShape } from './WorldScene'
import type { CharacterActivity, CharacterVisual } from './WorldScene'
import './CharacterPreview.css'
import { previewFraming } from './previewFraming'

export type RenderReport = {
  status: 'checking' | 'passed' | 'failed' | 'unavailable'
  schema_version: 'renderer-v3-rigid-object-rig'
  checks: { finite: boolean; bounds: boolean; visible: boolean; animations: string[] }
  errors: string[]
  bounds?: { width: number; height: number; depth: number }
  captured_at: string
}
type Props = { fighter: CharacterVisual; label?: string; scope?: string; compact?: boolean; presentation?: 'standard' | 'hero'; onReport?: (report: RenderReport) => void }
const initialReport = (): RenderReport => ({ status: 'checking', schema_version: 'renderer-v3-rigid-object-rig', checks: { finite: false, bounds: false, visible: false, animations: [] }, errors: [], captured_at: new Date().toISOString() })

class PreviewBoundary extends Component<{ children: ReactNode; onError: () => void }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch() { this.props.onError() }
  render() { return this.state.failed ? null : this.props.children }
}

function PreviewRig({ fighter, motion, turning, onReport, onCanvas }: { fighter: CharacterVisual; motion: CharacterActivity; turning: boolean; onReport: (report: RenderReport) => void; onCanvas: (canvas: HTMLCanvasElement) => void }) {
  const root = useRef<Group>(null)
  const body = useRef<Group>(null)
  const frames = useRef(0)
  const verified = useRef(false)
  const shaderFailed = useRef(false)
  const started = useRef(0)
  const animations = useRef(new Set<string>())
  const sampledChecks = useRef({ finite: true, bounds: true, visible: true })
  const sampledErrors = useRef<string[]>([])
  const sampledBounds = useRef({ width: 0, height: 0, depth: 0 })
  const framedViewport = useRef('')
  const asset = useRef<'pending' | 'ready' | 'failed'>(fighter.visual_spec.template_id === 'generic' ? 'pending' : 'ready')
  const { camera, gl, size: viewport } = useThree()
  const assetState = useCallback((state: 'ready' | 'failed') => { asset.current = state }, [])
  useEffect(() => {
    onCanvas(gl.domElement)
    const previousShaderHandler = gl.debug.onShaderError
    gl.debug.onShaderError = () => { shaderFailed.current = true; verified.current = true; onReport({ ...initialReport(), status: 'failed', errors: ['The character shader could not compile.'] }) }
    const lost = (event: Event) => { event.preventDefault(); onReport({ ...initialReport(), status: 'unavailable', errors: ['WebGL context was lost. 3D verification is unavailable.'] }) }
    gl.domElement.addEventListener('webglcontextlost', lost)
    return () => { gl.domElement.removeEventListener('webglcontextlost', lost); gl.debug.onShaderError = previousShaderHandler }
  }, [gl, onCanvas, onReport])
  useFrame(({ clock }) => {
    if (!root.current || !body.current) return
    if (!started.current) started.current = clock.elapsedTime
    const time = clock.elapsedTime - started.current
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    root.current.rotation.y = turning && !reduce ? time * .45 : -.28
    animateCharacterBody(body.current, fighter.visual_spec.animation_style, motion, time, 0, reduce)
    const frameKey = `${viewport.width}:${viewport.height}`
    if (asset.current !== 'pending' && framedViewport.current !== frameKey && camera instanceof PerspectiveCamera) {
      root.current.updateWorldMatrix(true, true)
      const box = new Box3().setFromObject(root.current)
      if (!box.isEmpty() && [...box.min.toArray(), ...box.max.toArray()].every(Number.isFinite)) {
        const frame = previewFraming(box, viewport.width / Math.max(1, viewport.height), camera.fov)
        const center = new Vector3(0, frame.centerY, 0)
        camera.position.copy(new Vector3(.9, .65, 1.8).normalize().multiplyScalar(frame.distance).add(center))
        camera.lookAt(center)
        camera.updateMatrixWorld()
        framedViewport.current = frameKey
      }
    }
    if (verified.current) return
    if (asset.current === 'pending' && time < 12) return
    frames.current += 1
    // Exercise each supported state through the same pose code used by the island.
    // This scene has no service imports and makes no battle/world writes.
    const state: CharacterActivity = frames.current < 4 ? 'idle' : frames.current < 8 ? 'rest' : 'wander'
    animateCharacterBody(body.current, fighter.visual_spec.animation_style, state, frames.current / 10, 0, reduce)
    if (![3, 7, 12].includes(frames.current)) return
    root.current.updateWorldMatrix(true, true)
    const box = new Box3().setFromObject(root.current)
    const size = box.getSize(new Vector3())
    const finite = [...box.min.toArray(), ...box.max.toArray()].every(Number.isFinite)
    const bounded = finite && Math.min(size.x, size.y, size.z) > .01 && Math.max(size.x, size.y, size.z) < 5
    let meshCount = 0
    root.current.traverse(node => { if (node instanceof Mesh && node.visible && node.geometry.getAttribute('position')?.count) meshCount += 1 })
    const corners = [box.min.x, box.max.x].flatMap(x => [box.min.y, box.max.y].flatMap(y => [box.min.z, box.max.z].map(z => new Vector3(x, y, z))))
    const projected = corners.map(point => point.project(camera))
    let pixelsVisible = false
    let pixelError = ''
    const target = new WebGLRenderTarget(64, 64)
    const previousTarget = gl.getRenderTarget()
    const previousColor = gl.getClearColor(new Color())
    const previousAlpha = gl.getClearAlpha()
    try {
      // Draw only the actual character, with the same geometry/materials/camera,
      // so a visible ground plane cannot make an invisible fighter pass.
      const isolated = new Scene()
      isolated.add(root.current.clone(true))
      isolated.add(new AmbientLight('#FFF9EB', 1.4))
      const light = new DirectionalLight('#FFF9EB', 2)
      light.position.set(-3, 5, 4); isolated.add(light)
      gl.setRenderTarget(target); gl.setClearColor('#000000', 0); gl.clear()
      gl.render(isolated, camera)
      const pixels = new Uint8Array(64 * 64 * 4)
      gl.readRenderTargetPixels(target, 0, 0, 64, 64, pixels)
      let covered = 0
      for (let index = 3; index < pixels.length; index += 4) if (pixels[index] > 0) covered += 1
      pixelsVisible = covered > 8 && !shaderFailed.current
    } catch { pixelError = 'The actual rendered visibility check could not complete.' }
    finally { gl.setRenderTarget(previousTarget); gl.setClearColor(previousColor, previousAlpha); target.dispose() }
    const visible = finite && meshCount > 0 && pixelsVisible && projected.every(point => Math.abs(point.x) < .99 && Math.abs(point.y) < .99 && point.z >= -1 && point.z <= 1)
    const errors = [pixelError, shaderFailed.current && 'The character shader could not compile.', !finite && 'Non-finite character bounds.', !bounded && 'Character bounds are empty or outside the supported preview.', !visible && 'Character is not fully visible in the standard view.', asset.current !== 'ready' && 'The original photo texture could not be loaded.'].filter(Boolean) as string[]
    animations.current.add(state)
    sampledChecks.current.finite &&= finite
    sampledChecks.current.bounds &&= bounded
    sampledChecks.current.visible &&= visible
    sampledErrors.current.push(...errors.map(error => `${state}: ${error}`))
    sampledBounds.current.width = Math.max(sampledBounds.current.width, size.x)
    sampledBounds.current.height = Math.max(sampledBounds.current.height, size.y)
    sampledBounds.current.depth = Math.max(sampledBounds.current.depth, size.z)
    if (frames.current < 12) return
    verified.current = true
    onReport({ status: sampledErrors.current.length ? 'failed' : 'passed', schema_version: 'renderer-v3-rigid-object-rig', checks: { ...sampledChecks.current, animations: [...animations.current] }, bounds: sampledBounds.current, errors: sampledErrors.current.slice(0, 10), captured_at: new Date().toISOString() })
  })
  return <>
    <color attach="background" args={['#EEE9DC']} />
    <ambientLight intensity={.7} />
    <hemisphereLight args={['#FFFBEE', '#9CAC98', 1.2]} />
    <directionalLight position={[-3, 5, 4]} intensity={2.1} castShadow shadow-mapSize={[512, 512]} shadow-camera-left={-3} shadow-camera-right={3} shadow-camera-top={4} shadow-camera-bottom={-2} shadow-normalBias={.025} />
    <mesh position={[0, -.04, 0]} receiveShadow><cylinderGeometry args={[1.55, 1.65, .08, 48]} /><meshStandardMaterial color="#DFD6BF" roughness={.9} /></mesh>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, .005, 0]}><ringGeometry args={[1.2, 1.21, 64]} /><meshBasicMaterial color="#B9AD93" /></mesh>
    <group ref={root} scale={characterDisplayScale(fighter)}><group ref={body}><CharacterShape character={fighter} onAssetState={assetState} /></group></group>
  </>
}

function validSpec(fighter: CharacterVisual) {
  const spec = fighter?.visual_spec
  return !!spec && ['mug', 'bottle', 'plant', 'book', 'ball', 'generic'].includes(spec.template_id) && Array.isArray(spec.palette) && spec.palette.length > 0 && spec.palette.every(color => /^#[a-f\d]{6}$/i.test(color)) && Array.isArray(spec.accessories) && spec.accessories.every(value => ['eyes', 'arms', 'feet', 'leaf', 'handle', 'cap'].includes(value)) && ['bouncy', 'calm', 'wobbly'].includes(spec.animation_style) && [spec.scale, spec.proportions?.width, spec.proportions?.height].every(value => Number.isFinite(value) && value >= .7 && value <= 1.4) && Number.isFinite(spec.appearance_seed)
}

export default function CharacterPreview({ fighter, label, scope, compact = false, presentation = 'standard', onReport }: Props) {
  const [report, setReport] = useState<RenderReport>(initialReport)
  const [motion, setMotion] = useState<CharacterActivity>('idle')
  const [turning, setTurning] = useState(false)
  const [supported, setSupported] = useState<boolean | null>(null)
  const canvas = useRef<HTMLCanvasElement | null>(null)
  const onReportRef = useRef(onReport)
  onReportRef.current = onReport
  const identity = JSON.stringify([fighter.visual_spec, fighter.image_ref, fighter.object_type, fighter.canonical_type_id, fighter.observed_object])
  const valid = validSpec(fighter)
  const publish = useCallback((value: RenderReport) => { setReport(value); onReportRef.current?.(value) }, [])
  const saveCanvas = useCallback((value: HTMLCanvasElement) => { canvas.current = value }, [])
  const runtimeError = useCallback(() => publish({ ...initialReport(), status: 'failed', errors: ['The character renderer encountered an error.'] }), [publish])
  useEffect(() => {
    publish(initialReport())
    if (!valid) { setSupported(false); publish({ ...initialReport(), status: 'failed', errors: ['This appearance does not match the supported renderer schema.'] }); return }
    try {
      const probe = document.createElement('canvas')
      const context = probe.getContext('webgl2')
      const available = !!context
      context?.getExtension('WEBGL_lose_context')?.loseContext()
      setSupported(available)
      if (!available) publish({ ...initialReport(), status: 'unavailable', errors: ['WebGL is unavailable. The source photograph remains available; this is not a passed 3D check.'] })
    } catch { setSupported(false); publish({ ...initialReport(), status: 'unavailable', errors: ['WebGL could not be opened in this browser.'] }) }
  }, [identity, valid, publish])
  const capture = () => {
    if (!canvas.current) return
    try {
      const link = document.createElement('a')
      link.download = 'sketch-clash-character-preview.png'
      link.href = canvas.current.toDataURL('image/png')
      link.click()
    } catch { publish({ ...report, status: 'failed', errors: [...report.errors, 'PNG capture was unavailable.'] }) }
  }
  return <div className={`character-preview ${compact ? 'is-compact' : ''}`}>
    <div className="character-preview-heading"><span>{scope ?? label ?? 'Fighter preview'}</span><span aria-label={`Rendering check ${report.status}`} title="Checks geometry, visibility and animation. You decide whether the character resembles your object." className={`preview-verdict is-${report.status}`}>{report.status === 'passed' ? <Check size={12} /> : report.status === 'checking' ? <RotateCw size={12} /> : <CircleAlert size={12} />}{report.status === 'passed' ? 'Render OK' : report.status === 'checking' ? 'Checking render' : `Render ${report.status}`}</span></div>
    <div className="character-preview-stage">
      {supported === true && <PreviewBoundary key={identity} onError={runtimeError}><Canvas shadows="percentage" dpr={[1, 1.5]} camera={{ position: presentation === 'hero' ? [2.4, 1.9, 3.6] : [2.8, 2.5, 5.8], fov: presentation === 'hero' ? 32 : 42, near: .1, far: 30 }} onCreated={({ camera }) => { camera.lookAt(0, presentation === 'hero' ? .7 : 1.3, 0); camera.updateProjectionMatrix() }} gl={{ antialias: true, preserveDrawingBuffer: true, powerPreference: 'low-power' }} aria-label={`${fighter.display_name ?? fighter.object_type ?? 'Object'} procedural character preview`}><PreviewRig fighter={fighter} motion={motion} turning={turning} onReport={publish} onCanvas={saveCanvas} /></Canvas></PreviewBoundary>}
      {supported === null && <span className="preview-unavailable">Opening the character studio…</span>}
      {(supported === false || report.status === 'failed') && <div className="preview-unavailable"><CircleAlert size={25} /><span>{report.errors[0] ?? '3D preview unavailable.'}</span></div>}
    </div>
    {!compact && <div className="character-preview-controls"><div>{(['idle', 'rest', 'wander'] as const).map(state => <button type="button" key={state} aria-pressed={motion === state} onClick={() => setMotion(state)}>{state}</button>)}</div><button type="button" aria-pressed={turning} disabled={supported !== true} onClick={() => setTurning(value => !value)} title="Turntable"><RotateCw size={14} /><span>Turntable</span></button><button type="button" disabled={report.status !== 'passed'} onClick={capture} title="Download preview PNG"><Camera size={14} /><span>PNG</span></button></div>}
    <p className="character-preview-note">{compact ? 'Stylised character · compare its shape with your photograph.' : 'Procedural character from the saved appearance and accepted visible features. Render OK checks visibility and animation; confirm resemblance against your photograph.'}</p>
  </div>
}
