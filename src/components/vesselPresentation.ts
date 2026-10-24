export type ObservedAppearance = { canonical_type_id?: string | null; label?: string | null; visible_features?: readonly string[] } | null
export type VesselInput = {
  canonical_type_id?: string
  object_type?: string
  observed_object?: ObservedAppearance
  visual_spec: { template_id: string; accessories: readonly string[]; proportions: { width: number; height: number } }
}
export type VesselPresentation = {
  kind: 'mug' | 'bottle' | 'tumbler'
  handle: boolean
  lid: boolean
  spout: boolean
  bodyHeight: number
  radiusTop: number
  radiusBottom: number
  neckHeight: number
  lidRadius: number
  basis: 'accepted_features' | 'saved_appearance'
}

const normalize = (value?: string | null) => (value ?? '').normalize('NFKC').toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
const mugs = new Set(['mug', 'ceramic mug', 'coffee mug', 'tea mug', 'cup', 'coffee cup', 'teacup'])
const bottles = new Set(['bottle', 'water bottle', 'plastic bottle', 'glass bottle', 'insulated bottle', 'tumbler', 'travel mug', 'insulated tumbler', 'water tumbler'])
const family = (value?: string | null) => mugs.has(normalize(value)) ? 'mug' : bottles.has(normalize(value)) ? 'bottle' : null
const bounded = (value: number, low: number, high: number) => Math.min(high, Math.max(low, Number.isFinite(value) ? value : 1))

/** Presentation only. Accepted visible features may refine a supported vessel;
 * they never change identity, capabilities, battle stats or stored records.
 * Negative/uncertain evidence cannot grow a handle, lid, spout or new shape. */
export function vesselPresentation(character: VesselInput): VesselPresentation | null {
  const spec = character.visual_spec
  if (spec.template_id !== 'mug' && spec.template_id !== 'bottle') return null
  const known = [character.canonical_type_id, character.object_type].map(family).filter(Boolean)
  if (known.some(kind => kind !== spec.template_id)) return null
  const observed = character.observed_object
  const observedFamily = family(observed?.canonical_type_id)
  const observedLabelFamily = family(observed?.label)
  const accepted = (!normalize(observed?.canonical_type_id) || observedFamily === spec.template_id)
    && (!observedLabelFamily || observedLabelFamily === spec.template_id)
  const features = accepted && Array.isArray(observed?.visible_features)
    ? observed.visible_features.filter((value): value is string => typeof value === 'string').slice(0, 24).map(value => normalize(value.slice(0, 400))) : []
  const uncertain = /\b(?:maybe|might|possibly|possible|uncertain|unclear|hidden|obscured|not visible|cannot see|can't see|unknown)\b/
  const negative = /\b(?:no|not|without|absent|lacks?|missing|handleless|lidless|capless)\b/
  const state = (match: RegExp): boolean | undefined => {
    const relevant = features.filter(feature => match.test(feature))
    if (relevant.some(feature => negative.test(feature))) return false
    return relevant.some(feature => !uncertain.test(feature)) ? true : undefined
  }
  const visibleHandle = state(/\b(?:handle|handles|handled|handleless)\b/)
  const visibleLid = state(/\b(?:lid|lidded|lidless|cap|capped|capless|screw top|flip top)\b/)
  const handle = visibleHandle ?? spec.accessories.includes('handle')
  const lid = visibleLid ?? spec.accessories.includes('cap')
  const wideBody = state(/\b(?:tumbler|travel mug|wide (?:body|bodied|cylinder)|broad (?:body|bodied|cylinder)|neckless)\b/) === true
  const narrowNeck = state(/\b(?:narrow neck|bottle neck|long neck)\b/) === true
  const kind = spec.template_id === 'mug' ? 'mug' : wideBody && !narrowNeck ? 'tumbler' : 'bottle'
  // Shape changes happen in body dimensions. The full rig remains uniformly
  // scaled, so eyes, circular rims and limbs never stretch with saved ratios.
  const ratio = bounded(bounded(spec.proportions.width, .7, 1.4) / bounded(spec.proportions.height, .7, 1.4), .85, 1.15)
  const radius = (kind === 'mug' ? .46 : kind === 'tumbler' ? .46 : handle ? .40 : .33) * Math.sqrt(ratio)
  const bodyHeight = (kind === 'mug' ? .94 : kind === 'tumbler' ? 1.26 : 1.12) / Math.sqrt(ratio)
  const neckHeight = kind === 'bottle' ? .40 : 0
  return {
    kind, handle, lid,
    spout: lid && state(/\b(?:drink spout|drinking spout|spout cover|flip lid)\b/) === true,
    bodyHeight, radiusTop: radius,
    radiusBottom: radius * (kind === 'tumbler' ? .82 : kind === 'mug' ? .92 : 1.04),
    neckHeight, lidRadius: kind === 'bottle' ? .195 : radius + .025,
    basis: features.length ? 'accepted_features' : 'saved_appearance',
  }
}
