import { objectSilhouette } from './objectIdentity.ts'
import type { ObservedAppearance } from './vesselPresentation'

export type FurnitureFeatures = { cushion: boolean; cushionColor?: string; stretchers: boolean; taperedLegs: boolean }

/** Saved observations refine appearance only. Missing, uncertain or conflicting
 * evidence never invents a cushion, leg bracing or a different material. */
export function furniturePresentation(kind: 'table' | 'chair', observed?: ObservedAppearance): FurnitureFeatures {
  const normalize = (value?: string | null) => (value ?? '').normalize('NFKC').toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
  const canonical = normalize(observed?.canonical_type_id)
  const canonicalKind = objectSilhouette('generic', canonical)
  const labelKind = objectSilhouette('generic', observed?.label ?? '')
  const accepted = (!canonical || canonicalKind === kind) && (!labelKind || labelKind === kind)
  const features = accepted && Array.isArray(observed?.visible_features)
    ? observed.visible_features.filter((value): value is string => typeof value === 'string').slice(0, 24).map(value => normalize(value.slice(0, 400))) : []
  const negative = /\b(?:no|not|without|absent|lacks?|missing)\b/
  const uncertain = /\b(?:maybe|might|possibly|possible|uncertain|unclear|hidden|obscured|cannot see|can't see|unknown)\b/
  const evidence = (pattern: RegExp) => {
    const matching = features.filter(feature => pattern.test(feature))
    return matching.some(feature => negative.test(feature)) ? [] : matching.filter(feature => !uncertain.test(feature))
  }
  const cushion = kind === 'chair' ? evidence(/\b(?:seat cushion|cushioned seat|padded seat|upholstered seat)\b/) : []
  return {
    cushion: cushion.length > 0,
    cushionColor: cushion.some(feature => /\b(?:cream|ivory|off white)\b/.test(feature)) ? '#EEE3C8' : undefined,
    stretchers: evidence(/\b(?:stretchers?|leg braces?|cross braces?|horizontal (?:leg )?braces?)\b/).length > 0,
    taperedLegs: evidence(/\btapered (?:wooden |wood )?legs\b/).length > 0,
  }
}
