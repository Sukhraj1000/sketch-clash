/** Only choosing the photograph uses the capture budget. Human review and
 * network/permission waits can take as long as they need without pressure. */
export function captureTimerActive(stage: string, frameReady: boolean, confirming: boolean): boolean {
  return !confirming && ((stage === 'camera' && frameReady) || stage === 'selection' || stage === 'recapture')
}
