import type { LearningRecord, ObjectDossier } from './colonies'

export function cavityPresentation(dossier: ObjectDossier) {
  const properties = dossier.simulation_properties
  const model = properties?.cavity_model
  const labels: Record<string, string> = {
    observed_cavity: 'Cavity suggested by recorded features',
    observed_absence: 'Recorded solid proxy without a cavity',
    declared_simulation_cavity: 'Visual cavity unknown · vessel supplied by a game capability',
    conflicting_evidence: 'Conflicting cavity evidence · clarification needed',
    unknown: 'Cavity unknown · evidence missing',
  }
  return {
    label: model ? labels[model.status] || 'Cavity evidence unavailable' : properties?.apparent_cavity === true ? 'Possible container'
      : properties?.apparent_cavity === false ? 'Solid proxy recorded by an earlier model' : 'Cavity unknown · evidence missing',
    authority: model?.authority?.replaceAll('_', ' ') || '',
    detail: model?.detail || '',
  }
}

export function historicalEvidence(record: LearningRecord) {
  return Boolean(record.evidence_status && record.evidence_status !== 'current')
}

export function reflectionPresentation(dossier: ObjectDossier) {
  const model = dossier.simulation_properties?.reflection_model
  const labels: Record<string, string> = {
    observed_reflective_surface: 'Reflective surface recorded · directional light can be tested',
    observed_diffuse_surface: 'Diffuse surface recorded · no directional relay assumed',
    conflicting_evidence: 'Conflicting surface evidence · clarification needed',
    unknown: 'Reflection unknown · evidence missing',
  }
  return { label: labels[model?.status ?? 'unknown'] ?? labels.unknown,
    detail: model?.detail ?? 'No reflective-surface evidence is recorded. An object name or material alone cannot unlock a signal relay.' }
}
