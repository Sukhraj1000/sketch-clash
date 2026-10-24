import { useEffect, useState } from 'react'
import { useThree } from '@react-three/fiber'
import { CanvasTexture, SRGBColorSpace } from 'three'
import type { IslandProject } from '../lib/island'
import type { ProjectBenefit } from '../lib/projectBenefits'

/** A camera-facing nameplate attached to the saved build site, not an extra project. */
export default function ProjectMapLabel({ project, benefit, selected, factory, height }: { project: IslandProject; benefit: ProjectBenefit; selected: boolean; factory: boolean; height: number }) {
  const [texture, setTexture] = useState<CanvasTexture | null>(null)
  const invalidate = useThree(state => state.invalidate)
  const built = project.level > 0
  const status = built ? 'BUILT' : project.status === 'building' ? `BUILDING ${Math.min(99, Math.round(project.progress / Math.max(1, project.required_progress) * 100))}%` : 'PLANNED'
  useEffect(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 512; canvas.height = selected ? 190 : 132
    const context = canvas.getContext('2d')
    if (!context) return
    const owned = new CanvasTexture(canvas)
    owned.colorSpace = SRGBColorSpace
    context.fillStyle = factory ? 'rgba(28, 37, 40, .97)' : 'rgba(255, 249, 235, .97)'
    context.beginPath(); context.roundRect(3, 3, 506, canvas.height - 9, 12); context.fill()
    context.lineWidth = selected ? 5 : 2
    context.strokeStyle = selected ? '#E9BC4B' : factory ? '#758A88' : '#D9CEB3'; context.stroke()
    const accent = benefit.status === 'active' ? factory ? '#A6D3BA' : '#37674D' : factory ? '#D5BC7B' : '#7C6840'
    context.fillStyle = accent; context.fillRect(4, 24, 6, canvas.height - 50)
    context.textAlign = 'left'; context.textBaseline = 'middle'
    const offset = selected ? 49 : 0
    if (selected) {
      context.fillStyle = accent; context.font = '700 27px sans-serif'
      context.fillText(`${status} · ${project.assembly?.family?.toUpperCase() ?? `LEVEL ${project.level}`}`, 22, 31, 468)
    }
    context.font = '700 36px sans-serif'; context.fillStyle = factory ? '#F2EFE3' : '#272C28'
    const name = project.name.length > 26 ? `${project.name.slice(0, 25)}…` : project.name
    context.fillText(name, 22, 40 + offset, 468)
    context.font = '500 33px sans-serif'; context.fillStyle = accent
    context.fillText(benefit.label, 22, 91 + offset, 468)
    owned.needsUpdate = true; setTexture(owned); invalidate()
    return () => owned.dispose()
  }, [benefit.label, benefit.status, factory, invalidate, project.assembly?.family, project.level, project.name, selected, status])
  return texture ? <sprite name={`project-label-${project.id}`} position={[0, height, 0]} scale={[selected ? 3.2 : 2.9, selected ? 1.1875 : .7477, 1]} renderOrder={3}>
    <spriteMaterial map={texture} toneMapped={false} depthWrite={false} />
  </sprite> : null
}
