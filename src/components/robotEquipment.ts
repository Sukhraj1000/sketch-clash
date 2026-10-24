export type RobotModule = 'water' | 'plan' | 'measure' | 'charge' | 'signal' | 'build' | 'carry' | 'none'

/** A visual accessory describes a recorded permission; it never grants a new action. */
export function robotEquipment(allowedActions: readonly string[] = []): { id: RobotModule; label: string } {
  const actions = new Set(allowedActions)
  if (actions.has('water') || actions.has('tend')) return { id: 'water', label: 'Water module' }
  if (actions.has('plan')) return { id: 'plan', label: 'Drafting module' }
  if (actions.has('measure')) return { id: 'measure', label: 'Measurement module' }
  if (actions.has('charge')) return { id: 'charge', label: 'Charging module' }
  if (actions.has('signal')) return { id: 'signal', label: 'Signal module' }
  if (actions.has('build')) return { id: 'build', label: 'Tool module' }
  if (actions.has('carry')) return { id: 'carry', label: 'Carry module' }
  return { id: 'none', label: 'General chassis' }
}
