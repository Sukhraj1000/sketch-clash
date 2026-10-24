export type ObjectActivity = 'idle' | 'rest' | 'wander'
export type ObjectWork = 'forage' | 'carry' | 'water' | 'plan' | 'measure' | 'charge' | 'signal' | 'tend' | 'build' | 'rest' | 'explore'

/** All pose changes are local presentation; no animation creates progress or edits agent state. */
export function objectPose(style: string, activity: ObjectActivity, seconds: number, seedPhase = 0, reducedMotion = false, work?: ObjectWork) {
  const time = Number.isFinite(seconds) ? seconds : 0
  const phase = Number.isFinite(seedPhase) ? seedPhase : 0
  const moving = activity === 'wander' && !reducedMotion
  const resting = activity === 'rest'
  const step = Math.sin(time * 7 + phase)
  const blinkPhase = ((time + phase * .83) % 5.6 + 5.6) % 5.6
  const blink = reducedMotion ? 1 : blinkPhase > 5.36 ? Math.max(.08, Math.abs(blinkPhase - 5.48) / .12) : 1
  const pose = {
    y: moving ? Math.abs(step) * (style === 'bouncy' ? .025 : .015) : 0,
    roll: moving ? step * (style === 'wobbly' ? .025 : .012) : 0,
    pitch: moving ? .015 : 0,
    yaw: moving || reducedMotion ? 0 : Math.sin(time * .7 + phase) * .015,
    scaleY: 1,
    blink: resting ? .45 : blink,
    leftArmX: moving ? step * .24 : 0,
    rightArmX: moving ? -step * .24 : 0,
    leftArmZ: -.18,
    rightArmZ: .18,
    leftFootX: moving ? -step * .22 : 0,
    rightFootX: moving ? step * .22 : 0,
    leftFootY: moving ? Math.max(0, step) * .025 : 0,
    rightFootY: moving ? Math.max(0, -step) * .025 : 0,
    tail: reducedMotion ? 0 : Math.sin(time * (moving ? 6 : 2.1) + phase) * .18,
    detail: reducedMotion ? 0 : Math.sin(time * 1.5 + phase) * .045,
  }
  if (!work || resting) return pose
  // Reduced motion still communicates the job through a fixed pose, without cycling it.
  const beat = reducedMotion ? 0 : Math.sin(time * 5 + phase)
  if (work === 'carry' || work === 'forage') { pose.leftArmX = -.65; pose.rightArmX = -.65; pose.leftArmZ = -.12; pose.rightArmZ = .12 }
  else if (work === 'water' || work === 'tend') { pose.pitch = .035 + beat * .01; pose.rightArmX = -.45; pose.rightArmZ = .35; pose.leftArmX = -.25 }
  else if (work === 'plan') { pose.pitch = .025; pose.leftArmX = -.5; pose.rightArmX = -.5 + beat * .08; pose.rightArmZ = .12 }
  else if (work === 'measure') { pose.leftArmZ = -.6; pose.rightArmZ = .6; pose.yaw = beat * .025 }
  else if (work === 'build') { pose.rightArmX = -.5 + beat * .28; pose.leftArmX = -.2; pose.detail = beat * .12 }
  else if (work === 'signal' || work === 'charge') { pose.leftArmZ = -.65; pose.rightArmZ = .65 }
  return pose
}
