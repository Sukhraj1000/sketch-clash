import type { ColonyBoardEntry } from '../lib/colonies'
import { boardCommentary, boardExecutorNote, boardText } from '../lib/boardPresentation'

export function BoardMessageText({ entry }: { entry: ColonyBoardEntry }) {
  const commentary = boardCommentary(entry)
  const executorNote = boardExecutorNote(entry)
  return <>
    <p>{boardText(entry)}</p>
    {commentary && <p className="colony-executor-explanation"><b>Unverified model commentary:</b> {commentary}</p>}
    {executorNote && <p className="colony-executor-explanation"><b>Executor note:</b> {executorNote}</p>}
    {entry.request_reused && <small>{entry.effect || 'References an existing request; no new commitment or delivery.'}</small>}
  </>
}
