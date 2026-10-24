type BoardWording = { kind: string; origin: string; text: string; interpretation?: string | null }

/** Reports quote the executor; free-form model commentary cannot replace evidence. */
export function boardText(row: BoardWording): string {
  return row.kind === 'report' || row.origin !== 'model' ? row.text : row.interpretation || row.text
}

export function boardCommentary(row: BoardWording): string | null {
  return row.kind === 'report' && row.origin === 'model' && row.interpretation?.trim() && row.interpretation !== row.text
    ? row.interpretation : null
}

/** Do not repeat an executor note already included in the factual receipt text. */
export function boardExecutorNote(row: BoardWording): string | null {
  const note = row.interpretation?.trim()
  return row.origin === 'executor' && note && !boardText(row).includes(note) ? note : null
}
