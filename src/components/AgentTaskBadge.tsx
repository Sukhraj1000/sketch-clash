import { useEffect, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { CanvasTexture, SRGBColorSpace } from 'three'
import type { Sprite } from 'three'
import type { IslandAgent } from '../lib/island'
import { robotTaskState } from './robotMotion'

/** A small scene label shows real task phase, not fabricated output or dialogue. */
export default function AgentTaskBadge({ agent, selected, now, paused }: { agent: IslandAgent; selected: boolean; now: () => number; paused: boolean }) {
  const [texture, setTexture] = useState<CanvasTexture | null>(null)
  const sprite = useRef<Sprite>(null)
  const draw = useRef<(() => void) | null>(null)
  const invalidate = useThree(state => state.invalidate)
  useEffect(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 512; canvas.height = 156
    const context = canvas.getContext('2d')
    if (!context) return
    const owned = new CanvasTexture(canvas)
    owned.colorSpace = SRGBColorSpace
    let last = ''
    draw.current = () => {
      const state = robotTaskState(agent.task, agent.position, now(), paused)
      if (sprite.current) sprite.current.visible = selected || state.phase === 'working' || state.phase === 'travelling'
      const progress = state.phase === 'working' ? Math.round((state.progress - .45) / .55 * 20) / 20 : 0
      const key = `${state.label}:${progress}`
      if (key === last) return
      last = key
      const working = state.phase === 'working'
      const moving = state.phase === 'travelling'
      const accent = working ? '#A4D1BA' : moving ? '#D4C995' : '#AEBBC2'
      context.clearRect(0, 0, 512, 156)
      context.fillStyle = 'rgba(30, 39, 44, .94)'
      context.beginPath(); context.roundRect(3, 3, 506, 146, 12); context.fill()
      context.strokeStyle = selected ? '#D9E7EA' : '#617077'; context.lineWidth = selected ? 4 : 2; context.stroke()
      context.textBaseline = 'middle'; context.textAlign = 'center'
      context.font = '500 30px sans-serif'; context.fillStyle = '#D8DFDE'
      const name = agent.display_name.length > 22 ? `${agent.display_name.slice(0, 21)}…` : agent.display_name
      context.fillText(name, 256, 44, 460)
      context.font = '600 31px sans-serif'; context.fillStyle = accent
      context.fillText(state.label.toUpperCase(), 256, 100, 460)
      if (working) { context.fillStyle = accent; context.fillRect(16, 138, 480 * progress, 4) }
      owned.needsUpdate = true
    }
    draw.current(); setTexture(owned); invalidate()
    return () => { draw.current = null; owned.dispose() }
  }, [agent.task, agent.position, agent.display_name, now, paused, selected, invalidate])
  useFrame(() => draw.current?.())
  return texture ? <sprite ref={sprite} visible={selected} position={[0, 1.2, 0]} scale={[selected ? 2 : 1.5, selected ? .61 : .46, 1]} raycast={() => {}} renderOrder={4}>
    <spriteMaterial map={texture} toneMapped={false} depthWrite={false} />
  </sprite> : null
}
