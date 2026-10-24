import type { IslandProject } from '../lib/island'

/** Presentation only: dense approved sites keep their anchors and rigid proportions. */
export function assemblySiteScale(project: IslandProject, projects: IslandProject[] = [project]): number {
  if (project.kind !== 'assembly') return 1
  const distances = projects.filter(other => other.id !== project.id).map(other => Math.hypot(
    other.position.x - project.position.x, other.position.z - project.position.z,
  )).filter(Number.isFinite)
  if (!distances.length) return 1
  // The complete 2m site fits inside 90% of its nearest-neighbour spacing.
  // A small lower bound keeps old/coincident records selectable rather than invisible.
  return Math.max(.28, Math.min(1, Math.min(...distances) * .45))
}
