import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent, ReactNode } from 'react'
import './SketchCanvas.css'

type Point = { x: number; y: number }
type Stroke = { points: Point[]; color: string; size: number; tool: 'pen' | 'eraser' }
export type SketchCanvasProps = {
  player: 1 | 2
  duration: number
  onSubmit: (image: string) => void
  onCancel: () => void
}

const WIDTH = 1000
const HEIGHT = 620
const INKS = [
  { value: '#1E1C29', label: 'Midnight ink' },
  { value: '#E93F59', label: 'Coral ink' },
  { value: '#168F86', label: 'Teal ink' },
  { value: '#7856B6', label: 'Violet ink' },
]

function ToolIcon({ children }: { children: ReactNode }) {
  return <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
}

function renderStrokes(context: CanvasRenderingContext2D, strokes: Stroke[], width: number, height: number) {
  context.setTransform(1, 0, 0, 1, 0, 0)
  context.clearRect(0, 0, width, height)
  context.setTransform(width / WIDTH, 0, 0, height / HEIGHT, 0, 0)
  context.lineCap = 'round'
  context.lineJoin = 'round'
  for (const stroke of strokes) {
    const points = stroke.points
    if (!points.length) continue
    context.globalCompositeOperation = stroke.tool === 'eraser' ? 'destination-out' : 'source-over'
    context.strokeStyle = stroke.color
    context.fillStyle = stroke.color
    context.lineWidth = stroke.size
    if (points.length === 1) {
      context.beginPath()
      context.arc(points[0].x, points[0].y, stroke.size / 2, 0, Math.PI * 2)
      context.fill()
      continue
    }
    context.beginPath()
    context.moveTo(points[0].x, points[0].y)
    for (let index = 1; index < points.length - 1; index++) {
      const point = points[index]
      const next = points[index + 1]
      context.quadraticCurveTo(point.x, point.y, (point.x + next.x) / 2, (point.y + next.y) / 2)
    }
    const last = points[points.length - 1]
    context.lineTo(last.x, last.y)
    context.stroke()
  }
  context.globalCompositeOperation = 'source-over'
  context.setTransform(1, 0, 0, 1, 0, 0)
}

function findInkBounds(context: CanvasRenderingContext2D, width: number, height: number) {
  const pixels = context.getImageData(0, 0, width, height).data
  let left = width
  let right = -1
  let top = height
  let bottom = -1
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (pixels[(y * width + x) * 4 + 3] > 0) {
        left = Math.min(left, x)
        right = Math.max(right, x)
        top = Math.min(top, y)
        bottom = Math.max(bottom, y)
      }
    }
  }
  return right < left ? null : { left, top, width: right - left + 1, height: bottom - top + 1 }
}

/** Export only the player's original ink, with transparent, proportional padding. */
function exportDrawing(strokes: Stroke[]) {
  const source = document.createElement('canvas')
  source.width = WIDTH
  source.height = HEIGHT
  const context = source.getContext('2d', { willReadFrequently: true })
  if (!context) return null
  renderStrokes(context, strokes, WIDTH, HEIGHT)
  const bounds = findInkBounds(context, WIDTH, HEIGHT)
  if (!bounds) return null
  const padding = Math.max(20, Math.round(Math.max(bounds.width, bounds.height) * 0.06))
  const output = document.createElement('canvas')
  output.width = bounds.width + padding * 2
  output.height = bounds.height + padding * 2
  const target = output.getContext('2d')
  if (!target) return null
  target.drawImage(source, bounds.left, bounds.top, bounds.width, bounds.height, padding, padding, bounds.width, bounds.height)
  return output.toDataURL('image/png')
}

export function SketchCanvas({ player, duration, onSubmit, onCancel }: SketchCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const strokesRef = useRef<Stroke[]>([])
  const undoRef = useRef<Stroke[][]>([])
  const strokeRef = useRef<Stroke | null>(null)
  const pointerRef = useRef<number | null>(null)
  const frameRef = useRef<number | null>(null)
  const editableRef = useRef(false)
  const submittedRef = useRef(false)
  const deadlineRef = useRef<number | null>(null)
  const [tool, setTool] = useState<'pen' | 'eraser'>('pen')
  const [color, setColor] = useState(INKS[0].value)
  const [size, setSize] = useState(7)
  const [remaining, setRemaining] = useState(duration)
  const [started, setStarted] = useState(false)
  const [hasInk, setHasInk] = useState(false)
  const [undoCount, setUndoCount] = useState(0)
  const [status, setStatus] = useState('')

  const paint = useCallback(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d', { willReadFrequently: true })
    if (canvas && context) renderStrokes(context, strokesRef.current, canvas.width, canvas.height)
  }, [])

  const queuePaint = useCallback(() => {
    if (frameRef.current !== null) return
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null
      paint()
    })
  }, [paint])

  const checkInk = useCallback(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d', { willReadFrequently: true })
    const ink = !!(canvas && context && findInkBounds(context, canvas.width, canvas.height))
    setHasInk(ink)
    return ink
  }, [])

  const finishStroke = useCallback(() => {
    const canvas = canvasRef.current
    const capturedPointer = pointerRef.current
    pointerRef.current = null
    if (capturedPointer !== null && canvas?.hasPointerCapture(capturedPointer)) {
      canvas.releasePointerCapture(capturedPointer)
    }
    strokeRef.current = null
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    paint()
    const ink = checkInk()
    setUndoCount(undoRef.current.length)
    return ink
  }, [paint, checkInk])

  // Reset before paint when players change, so the second player never sees the first sketch.
  useLayoutEffect(() => {
    editableRef.current = false
    submittedRef.current = false
    deadlineRef.current = null
    pointerRef.current = null
    strokeRef.current = null
    strokesRef.current = []
    undoRef.current = []
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    setStarted(false)
    setRemaining(duration)
    setHasInk(false)
    setUndoCount(0)
    setTool('pen')
    setStatus('')
    paint()
  }, [player, duration, paint])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 3)
      const width = Math.max(1, Math.round(rect.width * dpr))
      const height = Math.max(1, Math.round(rect.height * dpr))
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
        paint()
      }
    }
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    window.addEventListener('resize', resize)
    resize()
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', resize)
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    }
  }, [paint])

  useEffect(() => {
    if (!started) return
    const tick = () => {
      const next = Math.max(0, Math.ceil(((deadlineRef.current ?? performance.now()) - performance.now()) / 1000))
      setRemaining(next)
      if (next === 0 && editableRef.current) {
        editableRef.current = false
        const ink = finishStroke()
        setStatus(ink ? 'Pencils down! Your fighter is ready to enter.' : 'No ink on this page. Head back to the lobby to try a new round.')
      }
    }
    tick()
    const interval = window.setInterval(tick, 100)
    return () => window.clearInterval(interval)
  }, [started, finishStroke])

  const start = () => {
    if (started || submittedRef.current) return
    deadlineRef.current = performance.now() + Math.max(1, duration) * 1000
    editableRef.current = true
    setRemaining(Math.max(1, duration))
    setStarted(true)
    setStatus('')
  }

  const pointFromEvent = (event: { clientX: number; clientY: number }) => {
    const rect = canvasRef.current!.getBoundingClientRect()
    return {
      x: Math.max(0, Math.min(WIDTH, (event.clientX - rect.left) * WIDTH / rect.width)),
      y: Math.max(0, Math.min(HEIGHT, (event.clientY - rect.top) * HEIGHT / rect.height)),
    }
  }

  const pointerDown = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!editableRef.current || pointerRef.current !== null || (event.pointerType === 'mouse' && event.button !== 0)) return
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    pointerRef.current = event.pointerId
    undoRef.current.push([...strokesRef.current])
    const stroke: Stroke = { points: [pointFromEvent(event)], color, size: tool === 'eraser' ? size * 4 : size, tool }
    strokeRef.current = stroke
    strokesRef.current.push(stroke)
    if (tool === 'pen') setHasInk(true)
    setUndoCount(undoRef.current.length)
    queuePaint()
  }

  const pointerMove = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!editableRef.current || pointerRef.current !== event.pointerId || !strokeRef.current) return
    event.preventDefault()
    const samples = event.nativeEvent.getCoalescedEvents?.() ?? [event.nativeEvent]
    for (const sample of samples.length ? samples : [event.nativeEvent]) {
      const point = pointFromEvent(sample)
      const last = strokeRef.current.points[strokeRef.current.points.length - 1]
      if (Math.hypot(point.x - last.x, point.y - last.y) >= 0.4) strokeRef.current.points.push(point)
    }
    queuePaint()
  }

  const pointerEnd = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (pointerRef.current === event.pointerId) finishStroke()
  }

  const undo = () => {
    if (!editableRef.current) return
    finishStroke()
    const previous = undoRef.current.pop()
    if (!previous) return
    strokesRef.current = previous
    paint()
    checkInk()
    setUndoCount(undoRef.current.length)
  }

  const clear = () => {
    if (!editableRef.current || !strokesRef.current.length) return
    finishStroke()
    undoRef.current.push([...strokesRef.current])
    strokesRef.current = []
    paint()
    setHasInk(false)
    setUndoCount(undoRef.current.length)
  }

  const submit = () => {
    if (!started || submittedRef.current) return
    finishStroke()
    const image = exportDrawing(strokesRef.current)
    if (!image) {
      setHasInk(false)
      setStatus('A fighter needs a little ink. Draw something first!')
      return
    }
    submittedRef.current = true
    editableRef.current = false
    onSubmit(image)
  }

  const locked = !started || remaining === 0
  const urgent = started && remaining <= 10

  return <section className={`sketch-screen sketch-player-${player}`} aria-label={`Player ${player} drawing studio`}>
    <div className="sketch-heading">
      <div className="sketch-heading-copy">
        <span className="sketch-eyebrow"><span /> ROUND 01 / THE SKETCHBOOK</span>
        <h1>DRAW YOUR <em>WILD SIDE.</em></h1>
        <p>Big claws. Tiny legs. Questionable anatomy. Make it yours.</p>
      </div>
      <div className={`sketch-clock ${urgent ? 'sketch-clock-urgent' : ''}`} aria-label={`${remaining} seconds remaining`}>
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="12" cy="13" r="8" /><path d="M9 2h6M12 5V2m0 7v5l3 2M18 5l2 2" /></svg>
        <span>{String(remaining).padStart(2, '0')}<small>s</small></span>
        <div className="sketch-clock-track"><div style={{ transform: `scaleX(${remaining / Math.max(1, duration)})` }} /></div>
      </div>
    </div>

    <div className="sketch-workspace">
      <div className="sketch-side-note" aria-hidden="true">no talent<br />required.<svg viewBox="0 0 85 60"><path d="M6 7Q15 45 63 34M51 20l14 15-20 8" /></svg></div>
      <div className="sketch-notebook">
        <div className="sketch-binding" aria-hidden="true">{Array.from({ length: 9 }, (_, index) => <i key={index} />)}</div>
        <div className="sketch-paper-top">
          <span className="sketch-player-badge"><b>P{player}</b> YOUR TURN</span>
          <span className="sketch-theme">THEME <strong>ANIMALS</strong><svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><ellipse cx="6" cy="8" rx="2.4" ry="3" transform="rotate(-25 6 8)" /><ellipse cx="11" cy="5" rx="2.1" ry="3" /><ellipse cx="17" cy="7" rx="2.1" ry="3" transform="rotate(25 17 7)" /><path d="M5 16c0-3 4-6 7-6s7 4 7 7-4 2-7 2-7 0-7-3Z" /></svg></span>
        </div>
        <div className={`sketch-canvas-surface ${tool === 'eraser' ? 'is-erasing' : ''} ${locked ? 'is-locked' : ''} ${!started ? 'is-ready' : ''}`}>
          <canvas ref={canvasRef} className="sketch-drawing-layer" aria-label={`Draw player ${player}'s animal here using a mouse, pen or touch`} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerEnd} onPointerCancel={pointerEnd} onLostPointerCapture={pointerEnd} />
          {!hasInk && started && remaining > 0 && <div className="sketch-canvas-hint" aria-hidden="true"><span>weird is a superpower.</span><small>Draw your animal here</small></div>}
          {started && remaining === 0 && <div className="sketch-times-up"><span>PENCILS DOWN!</span><small>{hasInk ? 'Your masterpiece is locked in.' : 'This page needs a fighter. Start a new round to try again.'}</small></div>}
          {!started && <div className="sketch-ready-overlay">
            <span className="sketch-ready-kicker">{player === 2 ? 'A LITTLE MYSTERY MAKES A GOOD FIGHT' : 'YOUR IMAGINATION. THEIR PROBLEM.'}</span>
            <div className="sketch-ready-sticker">P{player}</div>
            <h2>{player === 2 ? 'PASS THE SKETCHBOOK.' : 'PENCILS AT THE READY.'}</h2>
            <p>{player === 2 ? 'Player 1, look away. Player 2, your secret weapon awaits.' : `You have ${duration} seconds to bring an animal to life. There are no bad drawings here.`}</p>
            <button type="button" className="sketch-start-button" onClick={start}>I'M READY <span aria-hidden="true">↗</span></button>
            <small>Your timer starts when you’re ready.</small>
          </div>}
        </div>
        <div className="sketch-paper-bottom"><span>ORIGINAL INK. UNLIMITED ATTITUDE.</span><span>SKETCH No. 00{player}</span></div>
      </div>
      <span className="sketch-star-doodle" aria-hidden="true">✳</span>
    </div>

    <div className="sketch-bottom-bar">
      <div className="sketch-toolbar" role="toolbar" aria-label="Drawing tools">
        <button type="button" className={`sketch-tool ${tool === 'pen' ? 'is-selected' : ''}`} aria-label="Pen" title="Pen" aria-pressed={tool === 'pen'} disabled={locked} onClick={() => setTool('pen')}><ToolIcon><path d="m15 4 5 5M4 20l5-1L20 8a2 2 0 0 0-5-5L4 14l-1 7Z" /></ToolIcon></button>
        <button type="button" className={`sketch-tool ${tool === 'eraser' ? 'is-selected' : ''}`} aria-label="Eraser" title="Eraser" aria-pressed={tool === 'eraser'} disabled={locked} onClick={() => setTool('eraser')}><ToolIcon><path d="m4 13 9-10a2 2 0 0 1 3 0l5 5a2 2 0 0 1 0 3L11 21H7l-4-5a2 2 0 0 1 1-3Zm4-4 9 9M10 21h12" /></ToolIcon></button>
        <span className="sketch-toolbar-rule" />
        <div className="sketch-colors" aria-label="Ink colours">{INKS.map(ink => <button type="button" key={ink.value} className={`sketch-color ${color === ink.value ? 'is-selected' : ''}`} style={{ backgroundColor: ink.value }} aria-label={ink.label} title={ink.label} aria-pressed={color === ink.value} disabled={locked} onClick={() => { setColor(ink.value); setTool('pen') }} />)}</div>
        <span className="sketch-toolbar-rule" />
        <label className="sketch-brush-control"><span className="sketch-brush-dot" style={{ width: Math.max(4, size), height: Math.max(4, size) }} /><input type="range" aria-label="Brush size" min="3" max="18" step="1" value={size} disabled={locked} onChange={event => setSize(Number(event.target.value))} /><span className="sketch-brush-value">{size}</span></label>
        <span className="sketch-toolbar-rule" />
        <button type="button" className="sketch-tool" aria-label="Undo last stroke" title="Undo" disabled={locked || undoCount === 0} onClick={undo}><ToolIcon><path d="m8 4-5 5 5 5M3 9h11a6 6 0 0 1 0 12h-3" /></ToolIcon></button>
        <button type="button" className="sketch-tool" aria-label="Clear drawing" title="Clear canvas" disabled={locked || !hasInk} onClick={clear}><ToolIcon><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7" /></ToolIcon></button>
      </div>
      <button type="button" className="sketch-submit-button" disabled={!started || !hasInk} onClick={submit}>LOCK IN MY FIGHTER <span aria-hidden="true">→</span></button>
    </div>
    <div className="sketch-footnote"><button type="button" onClick={onCancel}>← Back to lobby</button><span role="status">{status || 'Your exact drawing becomes your fighter. Every glorious wonky line.'}</span><span className="sketch-counter">{player} / 2 FIGHTERS</span></div>
  </section>
}

export default SketchCanvas
