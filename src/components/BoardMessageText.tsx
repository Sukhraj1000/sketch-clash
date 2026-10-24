import type { ColonyBoardEntry } from '../lib/colonies'
import { boardCommentary, boardText } from '../lib/boardPresentation'

export function BoardMessageText({ entry }: { entry: ColonyBoardEntry }) {
  const commentary = boardCommentary(entry)
  return <>
    <p>{boardText(entry)}</p>
    {commentary && <p className="colony-executor-explanation"><b>Unverified model commentary:</b> {commentary}</p>}
    {entry.origin === 'executor' && entry.interpretation && entry.interpretation !== entry.text && <p className="colony-executor-explanation"><b>Executor note:</b> {entry.interpretation}</p>}
    {entry.request_reused && <small>{entry.effect || 'References an existing request; no new commitment or delivery.'}</small>}
  </>
}
