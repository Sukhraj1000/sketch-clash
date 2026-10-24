import type { WorldCharacter } from './WorldView'
import { FACTORY, FactoryBox as Box, FactoryPaint as Paint } from './FactoryPrimitives'
import { robotEquipment } from './robotEquipment'
import type { RobotModule } from './robotEquipment'

const ROBOT = { housing: '#69737A', steel: '#A8AFB3', rubber: '#202528', sensor: '#111B20', panel: '#D0D4D4' } as const

/** Modules describe saved capabilities, rather than adding new abilities to the resident. */
function Equipment({ id, accent }: { id: RobotModule; accent: string }) {
  if (id === 'none') return null
  return <group name={`factory-module-${id}`}>
    {id === 'water' ? <group position={[0, .43, -.21]}>
      <mesh castShadow><cylinderGeometry args={[.085, .085, .28, 20]} /><Paint color={ROBOT.steel} material="steel" /></mesh>
      {[-.075, .075].map(y => <mesh key={y} position={[0, y, 0]} castShadow><cylinderGeometry args={[.09, .09, .025, 20]} /><Paint color={ROBOT.rubber} material="rubber" /></mesh>)}
      <Box position={[0, 0, -.087]} size={[.04, .14, .008]} color={FACTORY.blue} material="glass" />
      <mesh position={[.105, -.07, .005]} castShadow><cylinderGeometry args={[.013, .013, .17, 10]} /><Paint color={ROBOT.rubber} material="rubber" /></mesh>
      <Box position={[.1, -.15, .035]} size={[.06, .035, .09]} color={ROBOT.steel} material="steel" />
    </group> : id === 'plan' ? <group position={[0, .48, -.19]} rotation={[-.2, 0, 0]}>
      <Box size={[.24, .19, .045]} color={ROBOT.housing} material="steel" />
      <Box position={[0, .008, -.027]} size={[.205, .135, .01]} color={ROBOT.sensor} material="glass" />
      {[-.036, .012, .06].map(y => <Box key={y} position={[-.018, y, -.034]} size={[.135, .008, .003]} color={FACTORY.teal} shadow={false} />)}
    </group> : id === 'charge' ? <group position={[0, .43, -.2]}>
      <Box size={[.245, .245, .09]} color={ROBOT.housing} material="steel" />
      {[-.08, -.04, 0, .04, .08].map(x => <Box key={x} position={[x, 0, -.055]} size={[.012, .19, .035]} color={ROBOT.steel} material="steel" />)}
      <Box position={[.13, .065, -.015]} size={[.025, .05, .035]} color={accent} />
      <Box position={[.13, -.005, -.015]} size={[.025, .035, .035]} color={ROBOT.rubber} material="rubber" />
    </group> : id === 'signal' ? <group position={[.13, .68, -.1]}>
      <Box size={[.065, .08, .065]} color={ROBOT.housing} material="steel" />
      <mesh position={[0, .13, 0]} castShadow><cylinderGeometry args={[.009, .012, .24, 10]} /><Paint color={ROBOT.rubber} material="rubber" /></mesh>
      <Box position={[0, .025, .036]} size={[.03, .013, .008]} color={accent} />
    </group> : id === 'measure' ? <group position={[.08, .44, -.205]}>
      <Box size={[.075, .25, .065]} color={ROBOT.steel} material="steel" />
      <Box position={[0, .11, -.045]} size={[.11, .07, .05]} color={ROBOT.housing} />
      <mesh position={[0, .11, -.075]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[.017, .017, .018, 16]} /><Paint color={ROBOT.sensor} material="glass" /></mesh>
      {[-.085, -.035, .015].map(y => <Box key={y} position={[.008, y, -.035]} size={[.04, .007, .004]} color={ROBOT.rubber} shadow={false} />)}
    </group> : id === 'build' ? <group position={[.08, .45, -.205]} rotation={[0, 0, -.12]}>
      <Box position={[0, -.06, 0]} size={[.045, .15, .045]} color={ROBOT.rubber} material="rubber" />
      <mesh position={[0, .04, 0]} rotation={[Math.PI / 2, 0, 0]} castShadow><cylinderGeometry args={[.043, .043, .13, 16]} /><Paint color={ROBOT.housing} material="steel" /></mesh>
      <mesh position={[0, .04, -.095]} rotation={[Math.PI / 2, 0, 0]} castShadow><cylinderGeometry args={[.01, .016, .07, 12]} /><Paint color={ROBOT.steel} material="steel" /></mesh>
      <Box position={[0, -.12, 0]} size={[.08, .04, .07]} color={accent} />
    </group> : <group position={[0, .32, -.22]}>
      <Box size={[.32, .025, .22]} color={ROBOT.steel} material="steel" />
      <Box position={[0, .035, -.1]} size={[.32, .07, .02]} color={ROBOT.housing} material="steel" />
      {[-1, 1].map(side => <Box key={side} position={[side * .15, .035, 0]} size={[.02, .07, .2]} color={ROBOT.housing} material="steel" />)}
    </group>}
  </group>
}

/** A grounded mobile manipulator: wheels, sensor mast and jointed tools, without a cartoon face. */
export default function RobotShape({ character, allowedActions = [] }: { character: Pick<WorldCharacter, 'visual_spec'>; allowedActions?: readonly string[] }) {
  const palette = character.visual_spec.palette.filter(color => /^#[0-9A-Fa-f]{6}$/.test(color))
  const color = palette[0] ?? FACTORY.teal
  const accent = palette[1] ?? FACTORY.yellow
  const equipment = robotEquipment(allowedActions)
  return <group name="sc-character" userData={{ rigKey: `factory-robot:${equipment.id}` }}>
    {[-1, 1].map(side => <group key={side} name={side < 0 ? 'sc-foot-left' : 'sc-foot-right'} position={[side * .235, .12, 0]} userData={{ restY: .12 }}>
      {[-1, 1].map(axle => <group key={axle} position={[0, 0, axle * .135]} rotation={[0, 0, Math.PI / 2]}>
        <mesh castShadow receiveShadow><cylinderGeometry args={[.12, .12, .075, 24]} /><Paint color={ROBOT.rubber} material="rubber" /></mesh>
        <mesh position={[0, -side * .041, 0]} castShadow><cylinderGeometry args={[.068, .068, .012, 20]} /><Paint color={ROBOT.steel} material="steel" /></mesh>
        <mesh position={[0, -side * .049, 0]}><cylinderGeometry args={[.025, .025, .014, 12]} /><Paint color={ROBOT.housing} material="steel" /></mesh>
      </group>)}
    </group>)}
    <Box position={[0, .205, 0]} size={[.43, .145, .41]} color={ROBOT.housing} material="steel" />
    <Box position={[0, .285, 0]} size={[.43, .025, .41]} color={ROBOT.steel} material="steel" />
    <Box position={[0, .18, .212]} size={[.37, .045, .025]} color={ROBOT.rubber} material="rubber" />
    <Box position={[0, .241, .211]} size={[.24, .025, .009]} color={color} />
    <Box position={[0, .45, -.035]} size={[.11, .32, .12]} color={ROBOT.steel} material="steel" />
    <Box position={[0, .465, .005]} size={[.275, .19, .205]} color={ROBOT.housing} material="steel" />
    <Box position={[0, .466, .113]} size={[.225, .145, .012]} color={ROBOT.panel} material="steel" />
    <Box position={[-.065, .47, .123]} size={[.025, .09, .008]} color={color} />
    <Box position={[.065, .49, .123]} size={[.035, .012, .008]} color={accent} />
    <mesh position={[0, .635, -.015]} castShadow><cylinderGeometry args={[.027, .027, .15, 16]} /><Paint color={ROBOT.steel} material="steel" /></mesh>
    <Box position={[0, .72, -.005]} size={[.21, .075, .135]} color={ROBOT.housing} material="steel" />
    <group name="sc-eyes" position={[0, .72, .072]}>
      <mesh rotation={[Math.PI / 2, 0, 0]} castShadow><cylinderGeometry args={[.031, .031, .035, 20]} /><Paint color={ROBOT.rubber} material="rubber" /></mesh>
      <mesh position={[0, 0, .022]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[.021, .021, .009, 20]} /><Paint color={ROBOT.sensor} material="glass" /></mesh>
    </group>
    <mesh position={[0, .78, -.005]} castShadow><cylinderGeometry args={[.065, .065, .045, 24]} /><Paint color={ROBOT.rubber} material="rubber" /></mesh>
    <mesh position={[0, .798, -.005]}><cylinderGeometry args={[.062, .062, .015, 24]} /><Paint color={ROBOT.steel} material="steel" /></mesh>
    {[-1, 1].map(side => <group key={side} name={side < 0 ? 'sc-arm-left' : 'sc-arm-right'} position={[side * .178, .52, .015]} rotation={[0, 0, side * .15]}>
      <mesh rotation={[0, 0, Math.PI / 2]} castShadow><cylinderGeometry args={[.054, .054, .065, 20]} /><Paint color={ROBOT.rubber} material="rubber" /></mesh>
      <Box position={[0, -.095, 0]} size={[.06, .18, .062]} color={ROBOT.steel} material="steel" />
      <Box position={[side * .034, -.075, 0]} size={[.008, .075, .045]} color={accent} />
      <mesh position={[0, -.19, 0]} rotation={[0, 0, Math.PI / 2]} castShadow><cylinderGeometry args={[.044, .044, .07, 20]} /><Paint color={ROBOT.housing} material="steel" /></mesh>
      <Box position={[0, -.19, .075]} size={[.055, .055, .14]} color={ROBOT.steel} material="steel" />
      <Box position={[0, -.19, .155]} size={[.08, .05, .045]} color={ROBOT.rubber} material="rubber" />
      {[-1, 1].map(finger => <Box key={finger} position={[finger * .032, -.19, .198]} size={[.018, .035, .065]} color={ROBOT.steel} material="steel" />)}
    </group>)}
    <Equipment id={equipment.id} accent={accent} />
  </group>
}
