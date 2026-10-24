import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { transformWithOxc } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { boardText, boardCommentary } from '../src/lib/boardPresentation.ts'

const report = { id: 'report-1', kind: 'report', origin: 'model', text: 'Pencil added 3 ideas.', interpretation: 'I generated 999 energy.' }
assert.equal(boardText(report), 'Pencil added 3 ideas.')
assert.equal(boardCommentary(report), 'I generated 999 energy.')
assert.equal(boardText({ ...report, kind: 'proposal' }), 'I generated 999 energy.')
assert.equal(boardCommentary({ ...report, kind: 'proposal' }), null)
assert.equal(boardCommentary({ ...report, interpretation: report.text }), null)
assert.equal(boardCommentary({ ...report, interpretation: '  ' }), null)
assert.equal(boardText({ ...report, origin: 'executor' }), report.text)
assert.equal(boardCommentary({ ...report, origin: 'executor' }), null)

// Render the actual component so the commentary cannot silently become an unlabelled headline.
const componentUrl = new URL('../src/components/BoardMessageText.tsx', import.meta.url)
const transformed = await transformWithOxc(readFileSync(componentUrl, 'utf8'), 'BoardMessageText.tsx', { jsx: { runtime: 'automatic' } })
const code = transformed.code.replace('"../lib/boardPresentation"', JSON.stringify(new URL('../src/lib/boardPresentation.ts', import.meta.url).href)).replace('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime')))
const { BoardMessageText } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const render = entry => renderToStaticMarkup(createElement(BoardMessageText, { entry }))
const html = render(report)
assert.match(html, /^<p>Pencil added 3 ideas\.<\/p>/)
assert.match(html, /<b>Unverified model commentary:<\/b> I generated 999 energy\./)
assert.ok(html.indexOf(report.text) < html.indexOf(report.interpretation))
assert.doesNotMatch(render({ ...report, origin: 'executor', interpretation: 'Storage had room.' }), /Unverified model commentary/)
assert.match(render({ ...report, origin: 'executor', interpretation: 'Storage had room.' }), /Executor note:/)
// Reply previews use the same text policy, including for historical reports.
assert.equal(boardText(report).slice(0, 100), report.text)
console.log('Board presentation regressions passed: factual reports, labelled commentary, executor notes and safe reply previews.')
