export type ObjectActivity = 'idle' | 'rest' | 'wander'
export type ObjectWork = 'forage' | 'carry' | 'water' | 'plan' | 'measure' | 'charge' | 'signal' | 'tend' | 'build' | 'rest' | 'explore'

/** All pose changes are local presentation; no animation creates progress or edits agent state. */
export function objectPose(style: string, activity: ObjectActivity, seconds: number, seedPhase = 0, reducedMotion = false, work?: ObjectWork) {
  const time = Number.isFinite(seconds) ? seconds : 0
  const phase = Number.isFinite(seedPhase) ? seedPhase : 0
  const moving = activity === 'wander' && !reducedMotion
  const resting = activity === 'rest'
  const step = Math.sin(time * 7 + phase)
  const breath = reducedMotion ? 0 : Math.sin(time * 1.65 + phase) * .01
  const blinkPhase = ((time + phase * .83) % 5.6 + 5.6) % 5.6
  const blink = reducedMotion ? 1 : blinkPhase > 5.36 ? Math.max(.08, Math.abs(blinkPhase - 5.48) / .12) : 1
  const pose = {
    y: moving ? Math.abs(step) * (style === 'bouncy' ? .065 : .035) : breath,
    roll: moving ? step * (style === 'wobbly' ? .075 : .035) : reducedMotion ? 0 : Math.sin(time * 1.2 + phase) * .009,
    pitch: resting ? -.075 : moving ? .035 : 0,
    yaw: moving || reducedMotion ? 0 : Math.sin(time * .7 + phase) * .025,
    scaleY: resting ? .96 + breath : 1,
    blink: resting ? .45 : blink,
    leftArmX: moving ? step * .42 : 0,
    rightArmX: moving ? -step * .42 : 0,
    leftArmZ: -.38,
    rightArmZ: .38,
    leftFootX: moving ? -step * .48 : 0,
    rightFootX: moving ? step * .48 : 0,
    leftFootY: moving ? Math.max(0, step) * .04 : 0,
    rightFootY: moving ? Math.max(0, -step) * .04 : 0,
    tail: reducedMotion ? 0 : Math.sin(time * (moving ? 6 : 2.1) + phase) * .18,
    detail: reducedMotion ? 0 : Math.sin(time * 1.5 + phase) * .045,
  }
  if (!work || resting) return pose
  // Reduced motion still communicates the job through a fixed pose, without cycling it.
  const beat = reducedMotion ? 0 : Math.sin(time * 5 + phase)
  if (work === 'carry' || work === 'forage') { pose.leftArmX = -1.05; pose.rightArmX = -1.05; pose.leftArmZ = -.16; pose.rightArmZ = .16; pose.pitch = .08 }
  else if (work === 'water' || work === 'tend') { pose.pitch = .17 + beat * .035; pose.rightArmX = -.65; pose.rightArmZ = .75; pose.leftArmX = -.45 }
  else if (work === 'plan') { pose.pitch = .12; pose.leftArmX = -.9; pose.rightArmX = -.8 + beat * .14; pose.rightArmZ = .15 }
  else if (work === 'measure') { pose.leftArmZ = -1; pose.rightArmZ = 1; pose.pitch = .08; pose.yaw = beat * .06 }
  else if (work === 'build') { pose.rightArmX = -.8 + beat * .65; pose.leftArmX = -.35; pose.roll = beat * .045; pose.y += Math.max(0, beat) * .025; pose.detail = beat * .2 }
  else if (work === 'signal' || work === 'charge') { pose.leftArmZ = -2.1; pose.rightArmZ = 2.1; pose.roll = beat * .025 }
  return pose
}
