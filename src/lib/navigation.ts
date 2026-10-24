import type { Phase } from '../types'
export function routePhase(hash: string): Phase {
  if (hash === '#/battles' || hash.startsWith('#/battles/')) return 'OBJECT_BATTLES'
  if (hash === '#/playground') return 'PLAYGROUND'
  if (hash === '#/observatory') return 'OBSERVATORY'
  if (hash === '#/quality') return 'QUALITY'
  if (hash === '#/islands' || hash === '#/islands/legacy') return 'WORLD'
  return 'HOME'
}
