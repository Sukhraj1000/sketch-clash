import type { ReactNode } from 'react'
import { ObjectArms, ObjectFace, ObjectFeet, ObjectMaterial as Paint } from './ObjectRig'
import type { ObjectSilhouette } from './objectIdentity'

const INK = '#1E1C29'
const PAPER = '#FFF9EB'
const METAL = '#A7BEC7'
type Props = { kind: ObjectSilhouette; color: string; accent: string; feet: boolean; eyes: boolean; arms: boolean }

/** Recognizable silhouettes are presentation only. The accepted identity, palette and proportions stay server-owned. */
export default function ObjectShapes({ kind, color, accent, feet, eyes, arms }: Props) {
  let body: ReactNode
  let face = { y: 1.03, z: .2, width: .11, size: 1 }
  let rig = { armWidth: .32, armY: .86, footWidth: .17, size: 1 }
  if (kind === 'pencil' || kind === 'pen') {
    face = { y: 1.04, z: .15, width: .085, size: .8 }
    rig = { armWidth: .2, armY: .86, footWidth: .13, size: .85 }
    body = kind === 'pencil' ? <>
      <mesh position={[0, .84, 0]} castShadow><cylinderGeometry args={[.17, .17, 1.13, 6]} /><Paint color={color} /></mesh>
      <mesh position={[0, .24, 0]}><cylinderGeometry args={[.175, .175, .14, 6]} /><Paint color={METAL} /></mesh>
      <mesh position={[0, .14, 0]} castShadow><cylinderGeometry args={[.16, .15, .1, 6]} /><Paint color={accent} /></mesh>
      <mesh position={[0, 1.51, 0]} castShadow><coneGeometry args={[.17, .24, 6]} /><Paint color="#E5BD86" /></mesh>
      <mesh position={[0, 1.65, 0]}><coneGeometry args={[.065, .14, 6]} /><Paint color={INK} /></mesh>
      <mesh position={[.095, .72, .12]}><boxGeometry args={[.025, .56, .015]} /><Paint color={accent} /></mesh>
    </> : <>
      <mesh position={[0, .82, 0]} castShadow><cylinderGeometry args={[.125, .14, 1.13, 10]} /><Paint color={color} /></mesh>
      <mesh position={[0, 1.45, 0]} castShadow><cylinderGeometry args={[.145, .145, .3, 10]} /><Paint color={accent} /></mesh>
      <mesh position={[0, 1.65, 0]}><cylinderGeometry args={[.09, .09, .1, 8]} /><Paint color={METAL} /></mesh>
      <mesh position={[.16, 1.35, 0]} castShadow><boxGeometry args={[.045, .38, .07]} /><Paint color={METAL} /></mesh>
      <mesh position={[0, .2, 0]} rotation={[0, 0, Math.PI]}><coneGeometry args={[.12, .2, 8]} /><Paint color={INK} /></mesh>
    </>
  } else if (kind === 'ruler') {
    face = { y: 1.13, z: .075, width: .12, size: .85 }
    rig = { armWidth: .28, armY: .9, footWidth: .18, size: .9 }
    body = <>
      <mesh position={[0, .87, 0]} castShadow><boxGeometry args={[.5, 1.43, .12]} /><Paint color={color} /></mesh>
      <mesh position={[0, 1.43, .068]}><torusGeometry args={[.065, .015, 5, 10]} /><Paint color={accent} /></mesh>
      {Array.from({ length: 11 }, (_, i) => <mesh key={i} position={[.19 - (i % 5 === 0 ? .035 : 0), .28 + i * .09, .066]}><boxGeometry args={[i % 5 === 0 ? .16 : .09, .014, .012]} /><Paint color={INK} /></mesh>)}
      <mesh position={[-.2, .78, .068]}><boxGeometry args={[.022, 1.16, .013]} /><Paint color={accent} /></mesh>
    </>
  } else if (kind === 'phone') {
    face = { y: 1.03, z: .105, width: .14, size: 1 }
    rig.armWidth = .39
    body = <>
      <mesh position={[0, .87, 0]} castShadow><boxGeometry args={[.72, 1.35, .16]} /><Paint color={color} /></mesh>
      <mesh position={[0, .91, .089]}><boxGeometry args={[.6, 1.06, .02]} /><Paint color="#273B4B" /></mesh>
      <mesh position={[0, 1.45, .105]}><boxGeometry args={[.2, .025, .012]} /><Paint color={INK} /></mesh>
      <mesh position={[0, .31, .105]}><circleGeometry args={[.045, 12]} /><Paint color={accent} /></mesh>
      {[0, 1, 2].map(i => <mesh key={i} position={[-.17 + i * .17, .52, .105]}><boxGeometry args={[.1, .1, .015]} /><Paint color={i === 1 ? accent : '#A7CECE'} /></mesh>)}
      <mesh position={[.372, 1.08, 0]}><boxGeometry args={[.025, .2, .08]} /><Paint color={accent} /></mesh>
    </>
  } else if (kind === 'television') {
    face = { y: 1.03, z: .147, width: .17, size: 1.05 }
    rig = { armWidth: .69, armY: .96, footWidth: .28, size: .95 }
    body = <>
      <mesh position={[0, 1.0, 0]} castShadow><boxGeometry args={[1.32, .91, .2]} /><Paint color={color} /></mesh>
      <mesh position={[0, 1.035, .111]}><boxGeometry args={[1.16, .71, .025]} /><Paint color={INK} /></mesh>
      <mesh position={[0, 1.035, .129]}><boxGeometry args={[1.06, .61, .012]} /><Paint color="#30485B" /></mesh>
      <mesh position={[-.34, 1.27, .141]} rotation={[0, 0, -.15]}><boxGeometry args={[.26, .025, .008]} /><Paint color="#799BA8" /></mesh>
      <mesh position={[0, .38, -.025]} castShadow><boxGeometry args={[.18, .36, .16]} /><Paint color={INK} /></mesh>
      <mesh position={[0, .22, .025]} castShadow><boxGeometry args={[.86, .1, .39]} /><Paint color={color} /></mesh>
      <mesh position={[.48, .605, .112]}><circleGeometry args={[.026, 8]} /><Paint color={accent} /></mesh>
      {[-.39, -.13, .13, .39].map(x => <mesh key={x} position={[x, .79, -.105]}><boxGeometry args={[.15, .025, .01]} /><Paint color={INK} /></mesh>)}
    </>
  } else if (kind === 'microwave') {
    face = { y: .86, z: .399, width: .13, size: .9 }
    rig = { armWidth: .69, armY: .81, footWidth: .34, size: .95 }
    body = <>
      <mesh position={[0, .76, 0]} castShadow><boxGeometry args={[1.31, .92, .74]} /><Paint color={color} /></mesh>
      <mesh position={[-.13, .77, .379]}><boxGeometry args={[.96, .74, .025]} /><Paint color={INK} /></mesh>
      <mesh position={[-.16, .78, .395]}><boxGeometry args={[.75, .52, .012]} /><Paint color="#314856" /></mesh>
      <mesh position={[-.16, .57, .406]}><boxGeometry args={[.58, .022, .008]} /><Paint color="#839DA4" /></mesh>
      <mesh position={[.3, .78, .456]} castShadow><boxGeometry args={[.065, .5, .095]} /><Paint color={accent} /></mesh>
      <mesh position={[.51, .76, .377]}><boxGeometry args={[.19, .69, .025]} /><Paint color={accent} /></mesh>
      <mesh position={[.51, 1.0, .396]}><boxGeometry args={[.145, .12, .015]} /><Paint color={INK} /></mesh>
      {[-1, 1].map(side => <mesh key={side} position={[.51 + side * .035, 1, .407]}><boxGeometry args={[.022, .047, .007]} /><Paint color="#C0DF88" /></mesh>)}
      {[0, 1, 2].map(i => <mesh key={i} position={[.51, .81 - i * .12, .399]}><circleGeometry args={[.038, 8]} /><Paint color={INK} /></mesh>)}
      {[0, 1, 2, 3].map(i => <mesh key={i} position={[.661, .63 + i * .105, -.08]}><boxGeometry args={[.012, .025, .37]} /><Paint color={INK} /></mesh>)}
    </>
  } else if (kind === 'lamp') {
    face = { y: 1.29, z: .31, width: .12, size: .9 }
    rig = { armWidth: .26, armY: .75, footWidth: .25, size: .85 }
    body = <>
      <mesh position={[0, .21, 0]} castShadow><cylinderGeometry args={[.4, .46, .16, 12]} /><Paint color={color} /></mesh>
      <mesh position={[-.12, .61, 0]} rotation={[0, 0, -.26]} castShadow><capsuleGeometry args={[.055, .65, 3, 6]} /><Paint color={accent} /></mesh>
      <mesh position={[.02, 1.01, 0]} rotation={[0, 0, .65]} castShadow><capsuleGeometry args={[.05, .36, 3, 6]} /><Paint color={METAL} /></mesh>
      <group name="sc-detail" position={[0, 1.3, 0]}>
        <mesh castShadow><cylinderGeometry args={[.17, .39, .4, 10]} /><Paint color={color} /></mesh>
        <mesh position={[0, -.205, 0]} rotation={[Math.PI / 2, 0, 0]}><circleGeometry args={[.32, 10]} /><meshStandardMaterial color="#FFE7A0" emissive="#FAD16B" emissiveIntensity={.25} /></mesh>
      </group>
    </>
  } else if (kind === 'battery') {
    face = { y: 1.0, z: .29, width: .12, size: .95 }
    rig.armWidth = .32
    body = <>
      <mesh position={[0, .84, 0]} castShadow><cylinderGeometry args={[.29, .29, 1.25, 12]} /><Paint color={color} /></mesh>
      <mesh position={[0, 1.36, 0]}><cylinderGeometry args={[.297, .297, .23, 12]} /><Paint color={accent} /></mesh>
      <mesh position={[0, 1.55, 0]} castShadow><cylinderGeometry args={[.12, .12, .12, 10]} /><Paint color={METAL} /></mesh>
      <mesh position={[0, .23, 0]}><cylinderGeometry args={[.3, .3, .07, 12]} /><Paint color={METAL} /></mesh>
      <mesh position={[0, 1.36, .303]}><boxGeometry args={[.14, .027, .015]} /><Paint color={PAPER} /></mesh><mesh position={[0, 1.36, .304]}><boxGeometry args={[.027, .14, .015]} /><Paint color={PAPER} /></mesh>
      {[0, 1, 2].map(i => <mesh key={i} position={[-.12 + i * .12, .55, .278]}><boxGeometry args={[.065, .16, .025]} /><Paint color={accent} /></mesh>)}
    </>
  } else if (kind === 'shoe') {
    face = { y: .59, z: .73, width: .14, size: .9 }
    rig = { armWidth: .43, armY: .69, footWidth: .25, size: .85 }
    body = <>
      <mesh position={[0, .29, .02]} scale={[.9, .2, 1.35]} castShadow><sphereGeometry args={[.52, 10, 7]} /><Paint color={accent} /></mesh>
      <mesh position={[0, .53, .12]} scale={[.82, .56, 1.18]} castShadow><sphereGeometry args={[.51, 10, 7]} /><Paint color={color} /></mesh>
      <mesh position={[0, .71, -.26]} castShadow><boxGeometry args={[.59, .46, .49]} /><Paint color={color} /></mesh>
      <mesh position={[0, .95, -.26]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.2, 10]} /><Paint color={INK} /></mesh>
      {[0, 1, 2].map(i => <mesh key={i} position={[0, .85 - i * .055, -.06 + i * .12]} rotation={[-.36, 0, 0]}><boxGeometry args={[.32, .035, .04]} /><Paint color={PAPER} /></mesh>)}
    </>
  } else if (kind === 'scissors') {
    face = { y: .87, z: .11, width: .105, size: .8 }
    rig = { armWidth: .12, armY: .85, footWidth: .2, size: .85 }
    body = <>
      {[-1, 1].map(side => <group key={side} name={side < 0 ? 'sc-detail-left' : 'sc-detail-right'} position={[0, .83, 0]} rotation={[0, 0, side * .2]} userData={{ restZ: side * .2, side }}>
        <mesh position={[side * .08, .4, 0]} castShadow><boxGeometry args={[.12, .8, .08]} /><Paint color={METAL} /></mesh>
        <mesh position={[side * .17, -.35, 0]} scale={[.8, 1.15, 1]} castShadow><torusGeometry args={[.19, .065, 6, 12]} /><Paint color={side < 0 ? color : accent} /></mesh>
      </group>)}
      <mesh position={[0, .84, .065]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[.085, .085, .08, 8]} /><Paint color={accent} /></mesh>
    </>
  } else if (kind === 'spoon') {
    face = { y: 1.34, z: .105, width: .11, size: .85 }
    rig = { armWidth: .12, armY: .8, footWidth: .12, size: .85 }
    body = <>
      <mesh position={[0, .67, 0]} castShadow><capsuleGeometry args={[.075, .94, 3, 8]} /><Paint color={color} /></mesh>
      <mesh position={[0, 1.36, 0]} scale={[.74, 1, .25]} castShadow><sphereGeometry args={[.35, 10, 7]} /><Paint color={color} /></mesh>
      <mesh position={[0, 1.36, .075]} scale={[.7, 1, .1]}><sphereGeometry args={[.27, 10, 7]} /><Paint color={accent} /></mesh>
    </>
  } else if (kind === 'keys') {
    face = { y: 1.26, z: .1, width: .1, size: .8 }
    rig = { armWidth: .13, armY: .86, footWidth: .14, size: .85 }
    body = <>
      <mesh position={[0, 1.26, 0]} castShadow><torusGeometry args={[.25, .09, 6, 14]} /><Paint color={color} /></mesh>
      <mesh position={[0, .66, 0]} castShadow><boxGeometry args={[.15, .82, .11]} /><Paint color={color} /></mesh>
      {[.36, .52].map(y => <mesh key={y} position={[.14, y, 0]} castShadow><boxGeometry args={[.28, .105, .11]} /><Paint color={color} /></mesh>)}
      <mesh position={[.18, .96, -.06]} rotation={[0, 0, .4]}><boxGeometry args={[.12, .67, .065]} /><Paint color={accent} /></mesh>
      <mesh position={[.31, .68, -.06]}><boxGeometry args={[.21, .1, .065]} /><Paint color={accent} /></mesh>
    </>
  } else if (kind === 'pitcher') {
    face = { y: .91, z: .37, width: .14, size: 1 }
    rig = { armWidth: .41, armY: .8, footWidth: .22, size: 1 }
    body = <>
      <mesh position={[0, .78, 0]} castShadow><cylinderGeometry args={[.42, .32, 1.08, 10]} /><Paint color={color} /></mesh>
      <mesh position={[0, 1.325, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.33, 10]} /><Paint color="#385B6A" /></mesh>
      <mesh position={[.45, .85, 0]} rotation={[0, Math.PI / 2, 0]} scale={[1, 1.2, 1]} castShadow><torusGeometry args={[.29, .075, 6, 12]} /><Paint color={accent} /></mesh>
      <mesh position={[-.38, 1.25, 0]} rotation={[0, 0, -.9]} scale={[1, 1, .65]} castShadow><coneGeometry args={[.18, .36, 4]} /><Paint color={color} /></mesh>
      {[0, 1, 2].map(i => <mesh key={i} position={[-.24, .55 + i * .12, .29]}><boxGeometry args={[.1, .02, .015]} /><Paint color={accent} /></mesh>)}
    </>
  } else {
    const animal = kind
    face = { y: 1.21, z: .33, width: .13, size: .9 }
    rig = { armWidth: .38, armY: .77, footWidth: .21, size: .85 }
    body = <>
      <mesh position={[0, .63, 0]} scale={[.9, 1, .75]} castShadow><sphereGeometry args={[.45, 10, 7]} /><Paint color={color} /></mesh>
      <mesh position={[0, 1.16, 0]} scale={[1, 1, .92]} castShadow><sphereGeometry args={[.37, 10, 7]} /><Paint color={color} /></mesh>
      <mesh position={[0, .65, .3]} scale={[.75, 1, .2]}><sphereGeometry args={[.26, 8, 6]} /><Paint color={accent} /></mesh>
      {animal === 'cat' && [-1, 1].map(side => <group key={side} position={[side * .25, 1.48, 0]} rotation={[0, 0, side * -.12]}><mesh castShadow><coneGeometry args={[.17, .33, 3]} /><Paint color={color} /></mesh><mesh position={[0, .01, .055]} scale={[.6, .6, .4]}><coneGeometry args={[.17, .33, 3]} /><Paint color={accent} /></mesh></group>)}
      {animal === 'dog' && [-1, 1].map(side => <mesh key={side} position={[side * .36, 1.18, -.015]} rotation={[0, 0, side * .25]} scale={[.7, 1, .8]} castShadow><capsuleGeometry args={[.12, .3, 3, 7]} /><Paint color={accent} /></mesh>)}
      {animal === 'rabbit' && [-1, 1].map(side => <group key={side} position={[side * .15, 1.67, -.02]} rotation={[0, 0, side * -.15]}><mesh castShadow><capsuleGeometry args={[.09, .39, 3, 7]} /><Paint color={color} /></mesh><mesh position={[0, 0, .079]} scale={[.4, .75, .15]}><capsuleGeometry args={[.09, .39, 3, 7]} /><Paint color={accent} /></mesh></group>)}
      {animal === 'bear' && [-1, 1].map(side => <mesh key={side} position={[side * .28, 1.45, -.02]} castShadow><sphereGeometry args={[.14, 8, 6]} /><Paint color={accent} /></mesh>)}
      {animal === 'duck' ? <mesh position={[0, 1.03, .36]} scale={[1, .45, 1.1]} castShadow><sphereGeometry args={[.19, 8, 6]} /><Paint color={accent} /></mesh> : <mesh position={[0, 1.07, .34]} scale={[1, .75, .65]}><sphereGeometry args={[.095, 6, 5]} /><Paint color={INK} /></mesh>}
      <group name="sc-tail" position={[0, .55, -.3]}>
        {animal === 'cat' || animal === 'dog' ? <mesh position={[.1, .12, -.23]} rotation={[.75, 0, -.28]} castShadow><capsuleGeometry args={[animal === 'cat' ? .06 : .08, animal === 'cat' ? .55 : .3, 3, 7]} /><Paint color={color} /></mesh> : <mesh position={[0, 0, -.09]} castShadow><sphereGeometry args={[.14, 7, 5]} /><Paint color={accent} /></mesh>}
      </group>
    </>
  }
  return <group>
    {body}
    {feet && <ObjectFeet width={rig.footWidth} size={rig.size} />}
    {eyes && <ObjectFace {...face} />}
    {arms && <ObjectArms color={accent} width={rig.armWidth} y={rig.armY} size={rig.size} />}
  </group>
}
