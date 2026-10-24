import { computeTaskPose } from '../lib/island.ts'
import type { IslandPoint, IslandTask, IslandTaskKind } from '../lib/island.ts'

export type RobotTaskPhase = 'travelling' | 'working' | 'waiting' | 'scheduled' | 'settling' | 'paused'
const WORK_LABELS: Record<IslandTaskKind, string> = {
  carry: 'Handling supplies', forage: 'Gathering', water: 'Collecting water', tend: 'Tending',
  plan: 'Planning', measure: 'Measuring', charge: 'Charging', signal: 'Signalling',
  build: 'Assembling', explore: 'Exploring', rest: 'Waiting',
}

/** Read the executor's timeline; never imply completion before a saved receipt arrives. */
export function robotTaskState(task: IslandTask | null | undefined, position: IslandPoint, timeMs: number, paused = false) {
  const pose = computeTaskPose(task, position, timeMs)
  let phase: RobotTaskPhase = 'waiting'
  if (paused) phase = 'paused'
  else if (task) {
    if (pose.travelling) phase = 'travelling'
    else if (task.kind === 'rest') phase = 'waiting'
    else if (pose.working) phase = 'working'
    else if (pose.progress >= 1) phase = 'settling'
    else if (pose.progress === 0 || pose.progress < .45) phase = 'scheduled'
  }
  const job = task ? WORK_LABELS[task.kind] : 'Waiting'
  const label = phase === 'travelling' ? task?.kind === 'rest' ? 'Returning to standby' : `To ${task?.resource || (task?.project_id ? 'build site' : 'worksite')}`
    : phase === 'working' ? job : phase === 'settling' ? 'Awaiting receipt'
      : phase === 'scheduled' ? 'Preparing' : phase === 'paused' ? 'Paused' : 'Waiting for work'
  return { ...pose, phase, label }
}

/** Mechanical work poses only. No gait, squash, arbitrary patrols or output particles. */
export function robotWorkPose(kind: IslandTaskKind | undefined, working: boolean, travelling: boolean, seconds: number, reducedMotion = false) {
  const time = Number.isFinite(seconds) ? seconds : 0
  const beat = reducedMotion ? 0 : Math.sin(time * 3.5)
  const sweep = reducedMotion ? 0 : Math.sin(time * 1.4)
  const pose = { leftArmX: 0, rightArmX: 0, leftArmZ: -.15, rightArmZ: .15, toolX: 0, toolY: 0, toolZ: 0, toolTilt: 0, toolSpin: 0 }
  if (!working && !(travelling && (kind === 'carry' || kind === 'forage'))) return pose
  if (kind === 'carry' || kind === 'forage') {
    pose.leftArmX = -.7; pose.rightArmX = -.7
    if (working) { pose.leftArmX += beat * .17; pose.rightArmX += beat * .17; pose.toolY = beat * .055; pose.toolZ = sweep * .025 }
  } else if (kind === 'build') {
    pose.leftArmX = -.6; pose.rightArmX = -.9 + beat * .2
    pose.toolY = beat * .035; pose.toolZ = beat * .025; pose.toolSpin = reducedMotion ? 0 : time * 18
  } else if (kind === 'measure') {
    pose.leftArmX = -.5; pose.rightArmX = -.9; pose.rightArmZ = .18 + sweep * .12
    pose.toolX = sweep * .065; pose.toolTilt = sweep * .12
  } else if (kind === 'plan') {
    pose.leftArmX = -.7; pose.rightArmX = -.72 + beat * .13
  } else if (kind === 'water' || kind === 'tend') {
    pose.leftArmX = -.45; pose.rightArmX = -.85 + sweep * .1
    pose.toolTilt = -.3 + sweep * .12; pose.toolY = sweep * .015
  } else if (kind === 'charge' || kind === 'signal') {
    pose.leftArmX = -.3; pose.rightArmX = -.85; pose.rightArmZ = .3
  }
  return pose
}

/** Rolling angle comes from actual travel distance, so stationary wheels never spin. */
export function robotWheelAngle(task: IslandTask | null | undefined, position: IslandPoint, timeMs: number) {
  if (!task) return 0
  const pose = computeTaskPose(task, position, timeMs)
  const from = computeTaskPose(task, position, Date.parse(task.started_at))
  return Math.hypot(pose.x - from.x, pose.z - from.z) / .12
}

export type RobotWheelState = { taskId?: string; distanceAngle: number; angle: number }
export function advanceRobotWheels(previous: RobotWheelState, taskId: string | undefined, distanceAngle: number): RobotWheelState {
  const travelled = Math.max(0, Number.isFinite(distanceAngle) ? distanceAngle : 0)
  const delta = previous.taskId === taskId ? Math.max(0, travelled - previous.distanceAngle) : travelled
  return { taskId, distanceAngle: travelled, angle: previous.angle + delta }
}
