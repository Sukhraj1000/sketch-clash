import type { ReactNode } from 'react'
import { ObjectArms, ObjectFace, ObjectFeet, ObjectMaterial as Paint } from './ObjectRig'
import { CharacterShape } from './WorldScene'
import type { CharacterVisual } from './WorldScene'

type BattleObjectKind = 'sponge' | 'foam' | 'rope' | 'whisk'
const kinds: Record<string, BattleObjectKind> = {
  sponge: 'sponge', 'kitchen sponge': 'sponge',
  foam: 'foam', 'foam block': 'foam',
  rope: 'rope', 'coiled rope': 'rope',
  whisk: 'whisk', 'metal whisk': 'whisk',
}
const normalize = (value?: string) => (value ?? '').normalize('NFKC').trim().toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ')

/** These extra battle silhouettes only refine matching generic identities.
 * The accepted palette, accessories and all gameplay evidence stay intact. */
export default function BattleObjectShape({ character }: { character: CharacterVisual }) {
  const spec = character.visual_spec
  const label = normalize(character.object_type), canonical = normalize(character.canonical_type_id)
  const kind = kinds[label] ?? kinds[canonical]
  const conflictingIdentity = !!label && !!canonical && label !== canonical && kinds[label] !== kinds[canonical]
  if (spec.template_id !== 'generic' || !kind || conflictingIdentity) return <CharacterShape character={character} showSourceImage={false} />

  const palette = spec.palette.filter(color => /^#[0-9A-Fa-f]{6}$/.test(color))
  const color = palette[0] ?? '#66E0D4', accent = palette[1] ?? '#FFD166'
  let body: ReactNode
  let face = { y: .82, z: .32, width: .15, size: 1 }
  let arms = { width: .5, y: .82, size: 1 }
  let feet = { width: .25, size: 1 }

  if (kind === 'sponge') {
    body = <>
      <mesh position={[0, .68, 0]} castShadow><boxGeometry args={[.96, .82, .56]} /><Paint color={color} /></mesh>
      <mesh position={[0, 1.13, 0]} castShadow><boxGeometry args={[.98, .12, .58]} /><Paint color={accent} /></mesh>
      {[[-.33, .94, .045], [.3, .98, .035], [-.36, .47, .052], [.29, .43, .04], [0, .39, .025]].map(([x, y, radius], index) =>
        <mesh key={index} position={[x, y, .285]}><circleGeometry args={[radius, 7]} /><Paint color={accent} /></mesh>)}
    </>
  } else if (kind === 'foam') {
    face = { y: .86, z: .335, width: .17, size: 1 }
    arms = { width: .51, y: .85, size: 1 }
    body = <>
      <mesh position={[0, .74, 0]} castShadow><boxGeometry args={[.98, .94, .62]} /><Paint color={color} /></mesh>
      {[-.29, 0, .29].map(x => <mesh key={x} position={[x, 1.216, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.06, 8]} /><Paint color={accent} /></mesh>)}
      {[-.33, .33].map(x => <mesh key={x} position={[x, .49, .317]}><circleGeometry args={[.045, 8]} /><Paint color={accent} /></mesh>)}
      <mesh position={[0, .32, .317]}><boxGeometry args={[.73, .035, .015]} /><Paint color={accent} /></mesh>
    </>
  } else if (kind === 'rope') {
    face = { y: .83, z: .18, width: .16, size: .92 }
    arms = { width: .49, y: .79, size: .95 }
    feet = { width: .24, size: .95 }
    body = <>
      {[.18, .3, .42].map((radius, index) => <mesh key={radius} position={[0, .72, .02 - index * .025]} castShadow><torusGeometry args={[radius, .069, 6, 24]} /><Paint color={index === 1 ? accent : color} /></mesh>)}
      <mesh position={[0, .72, -.035]}><circleGeometry args={[.13, 12]} /><Paint color={accent} /></mesh>
      <group name="sc-tail" position={[.35, .42, -.04]}>
        <mesh rotation={[0, 0, -.7]} castShadow><torusGeometry args={[.22, .055, 6, 16, Math.PI * 1.45]} /><Paint color={color} /></mesh>
      </group>
    </>
  } else {
    face = { y: .62, z: .15, width: .085, size: .72 }
    arms = { width: .17, y: .64, size: .8 }
    feet = { width: .12, size: .8 }
    body = <>
      <mesh position={[0, .51, 0]} castShadow><cylinderGeometry args={[.13, .14, .57, 10]} /><Paint color={accent} /></mesh>
      <mesh position={[0, .82, 0]} castShadow><cylinderGeometry args={[.095, .13, .12, 10]} /><Paint color={color} /></mesh>
      <group name="sc-detail" position={[0, 1.1, 0]}>
        {[0, Math.PI / 3, Math.PI * 2 / 3].map(rotation => <mesh key={rotation} rotation={[0, rotation, 0]} scale={[.72, 1, 1]} castShadow><torusGeometry args={[.3, .023, 5, 22]} /><meshStandardMaterial color={color} metalness={.6} roughness={.35} /></mesh>)}
      </group>
    </>
  }

  return <group name="sc-character" userData={{ rigKey: `battle:${kind}:${spec.accessories.join(',')}` }}>
    {body}
    {spec.accessories.includes('feet') && <ObjectFeet {...feet} />}
    {spec.accessories.includes('arms') && <ObjectArms {...arms} color={accent} />}
    {spec.accessories.includes('eyes') && <ObjectFace {...face} />}
  </group>
}
