import type { WorldCharacter } from './WorldView'
import { FACTORY, FactoryBox as Box, FactoryPaint as Paint } from './FactoryPrimitives'
import { robotEquipment } from './robotEquipment'
import type { RobotModule } from './robotEquipment'

function Equipment({ id, accent }: { id: RobotModule; accent: string }) {
  if (id === 'none') return null
  return <group name={`factory-module-${id}`}>
    {id === 'water' ? <group position={[0, .42, -.2]}>
      <mesh castShadow><cylinderGeometry args={[.12, .12, .32, 8]} /><Paint color={FACTORY.blue} /></mesh>
      <Box position={[0, 0, -.11]} size={[.12, .22, .025]} color={FACTORY.paper} />
      <Box position={[.16, .05, .02]} size={[.14, .05, .05]} color={FACTORY.ink} />
    </group> : id === 'plan' ? <group position={[0, .42, -.215]}>
      <Box size={[.26, .28, .075]} color={FACTORY.ink} />
      <Box position={[0, 0, -.043]} size={[.2, .21, .018]} color={FACTORY.paper} />
      {[-.055, .015, .085].map(y => <Box key={y} position={[0, y, -.056]} size={[.12, .015, .008]} color={FACTORY.teal} shadow={false} />)}
    </group> : id === 'charge' ? <group position={[0, .42, -.21]}>
      <Box size={[.24, .3, .09]} color={FACTORY.ink} />
      {[-.085, 0, .085].map(y => <Box key={y} position={[0, y, -.053]} size={[.16, .055, .025]} color={accent} />)}
    </group> : id === 'signal' ? <group position={[.18, .81, -.03]}>
      <mesh position={[0, .095, 0]} castShadow><cylinderGeometry args={[.018, .018, .19, 6]} /><Paint color={FACTORY.ink} /></mesh>
      <mesh position={[0, .21, 0]} castShadow><sphereGeometry args={[.045, 8, 6]} /><Paint color={accent} glow /></mesh>
    </group> : id === 'measure' ? <group position={[.07, .45, -.23]} rotation={[0, 0, -.2]}>
      <Box size={[.09, .36, .06]} color={FACTORY.yellow} />
      {[-.12, -.04, .04, .12].map(y => <Box key={y} position={[.015, y, -.034]} size={[.05, .013, .008]} color={FACTORY.ink} shadow={false} />)}
    </group> : id === 'build' ? <group position={[.07, .45, -.23]} rotation={[0, 0, -.3]}>
      <Box size={[.045, .27, .05]} color={FACTORY.ink} />
      <Box position={[0, .15, 0]} size={[.18, .085, .08]} color={FACTORY.metal} />
    </group> : <group position={[0, .3, -.2]}>
      <Box size={[.31, .045, .2]} color={accent} />
      <Box position={[0, .055, -.08]} size={[.31, .11, .035]} color={FACTORY.ink} />
    </group>}
  </group>
}

/** One compact, rigid robot rig, with the original object's palette and saved permissions. */
export default function RobotShape({ character, allowedActions = [] }: { character: Pick<WorldCharacter, 'visual_spec'>; allowedActions?: readonly string[] }) {
  const palette = character.visual_spec.palette.filter(color => /^#[0-9A-Fa-f]{6}$/.test(color))
  const color = palette[0] ?? FACTORY.teal
  const accent = palette[1] ?? FACTORY.yellow
  const equipment = robotEquipment(allowedActions)
  return <group name="sc-character" userData={{ rigKey: `factory-robot:${equipment.id}` }}>
    {[-1, 1].map(side => <group key={side} name={side < 0 ? 'sc-foot-left' : 'sc-foot-right'} position={[side * .12, .09, 0]} userData={{ restY: .09 }}>
      <Box position={[0, .065, -.02]} size={[.065, .14, .065]} color={FACTORY.metal} />
      <Box position={[0, -.035, .035]} size={[.17, .11, .22]} color={FACTORY.ink} />
      <Box position={[0, -.015, .144]} size={[.12, .035, .015]} color={accent} />
    </group>)}
    <Box position={[0, .36, 0]} size={[.39, .32, .31]} color={FACTORY.ink} />
    <Box position={[0, .37, .022]} size={[.35, .29, .31]} color={color} />
    <Box position={[0, .39, .183]} size={[.23, .17, .02]} color={FACTORY.paper} />
    <Box position={[-.055, .4, .199]} size={[.075, .075, .015]} color={accent} />
    {[.36, .41].map(y => <Box key={y} position={[.055, y, .2]} size={[.07, .014, .012]} color={FACTORY.ink} shadow={false} />)}
    <Box position={[0, .55, 0]} size={[.11, .11, .1]} color={FACTORY.metal} />
    <Box position={[0, .7, 0]} size={[.46, .28, .35]} color={FACTORY.ink} />
    <Box position={[0, .71, -.005]} size={[.42, .25, .34]} color={FACTORY.paper} />
    <Box position={[0, .71, .172]} size={[.34, .15, .025]} color={FACTORY.ink} />
    <group name="sc-eyes" position={[0, .715, .192]}>
      {[-1, 1].map(side => <mesh key={side} position={[side * .082, 0, 0]}><planeGeometry args={[.044, .06]} /><meshBasicMaterial color={FACTORY.teal} /></mesh>)}
    </group>
    <Box position={[0, .595, .177]} size={[.085, .018, .012]} color={accent} shadow={false} />
    {[-1, 1].map(side => <group key={side} name={side < 0 ? 'sc-arm-left' : 'sc-arm-right'} position={[side * .235, .48, 0]} rotation={[0, 0, side * .18]}>
      <mesh rotation={[0, 0, Math.PI / 2]} castShadow><cylinderGeometry args={[.062, .062, .075, 8]} /><Paint color={accent} /></mesh>
      <Box position={[0, -.09, 0]} size={[.075, .16, .075]} color={FACTORY.paper} />
      <Box position={[0, -.19, .01]} size={[.1, .09, .1]} color={FACTORY.ink} />
      {[-1, 1].map(finger => <Box key={finger} position={[finger * .035, -.22, .055]} size={[.025, .04, .06]} color={FACTORY.metal} />)}
    </group>)}
    <Equipment id={equipment.id} accent={accent} />
  </group>
}
