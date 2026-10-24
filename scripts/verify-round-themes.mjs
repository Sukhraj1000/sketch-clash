import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { transformWithOxc } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// Render the real review and capture screens without browser/provider requests.
// The 3D preview is substituted only in this server-rendered presentation test.
const modules = new Map()
async function sourceModule(url) {
  if (modules.has(url.href)) return modules.get(url.href)
  const { code: transformed } = await transformWithOxc(readFileSync(url, 'utf8'), url.pathname, { jsx: { runtime: 'automatic' } })
  let code = transformed.replace(/^\s*import\s+['"][^'"]+\.css['"];?\s*$/gm, '')
    .replace(/import\(['"]\.\/CharacterPreview['"]\)/g, 'Promise.resolve({default:()=>null})')
  for (const match of [...code.matchAll(/\bfrom\s+(['"])([^'"]+)\1/g)]) {
    const specifier = match[2]
    let resolved
    if (specifier.startsWith('.')) {
      let dependency = new URL(specifier, url)
      if (!existsSync(dependency)) dependency = ['.ts', '.tsx'].map(extension => new URL(specifier + extension, url)).find(candidate => existsSync(candidate))
      assert.ok(dependency, `Resolve ${specifier}`)
      resolved = await sourceModule(dependency)
    } else resolved = import.meta.resolve(specifier)
    code = code.replace(match[0], `from ${JSON.stringify(resolved)}`)
  }
  const result = `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
  modules.set(url.href, result)
  return result
}

const { default: Review } = await import(await sourceModule(new URL('../src/components/FighterReview.tsx', import.meta.url)))
const { CaptureStudio } = await import(await sourceModule(new URL('../src/components/CaptureStudio.tsx', import.meta.url)))
const response = {capture_id:'saved',status:'recognized',image_url:'/fixture-photo',width:120,height:90,
  fighter:{display_name:'Kiln',object_type:'mug',visual_spec:{},image_ref:'/fixture-photo'},
  theme_validation:{theme_id:'animals',theme_name:'Animal Kingdom',policy_version:'round-themes-1',
    verdict:'outside_theme',reason:'A mug is outside Animal Kingdom. Correct the label or retake.',evidence_labels:['mug'],basis:'recognition_identity_rules'}}
const props = {onFeedback(){throw Error('No writes')},onCorrect(){throw Error('No writes')},onRevised(){},onConfirm(){throw Error('No writes')},onRetake(){}}
const blocked = renderToStaticMarkup(createElement(Review,{response,...props}))
assert.match(blocked,/OUTSIDE THE THEME · CAPTURE DISQUALIFIED/)
assert.match(blocked,/Choose another photograph/)
assert.match(blocked,/<button[^>]*class="review-confirm"[^>]*disabled=""/,'Even historical proposals cannot bypass theme eligibility')
const uncertain = renderToStaticMarkup(createElement(Review,{response:{...response,theme_validation:{...response.theme_validation,verdict:'uncertain',reason:'Unknown subject; use a clearer label.'}},...props}))
assert.match(uncertain,/THEME CHECK NEEDS A CLEARER IDENTITY/)
assert.doesNotMatch(uncertain,/CAPTURE DISQUALIFIED/)
assert.match(uncertain,/<button[^>]*class="review-confirm"[^>]*disabled=""/)
const eligible = renderToStaticMarkup(createElement(Review,{response:{...response,theme_validation:{...response.theme_validation,verdict:'eligible',reason:'Fits the brief.'}},...props}))
assert.match(eligible,/FITS THE ROUND/)
assert.doesNotMatch(eligible,/<button[^>]*class="review-confirm"[^>]*disabled/)

// Pricing integration renders its real component recursively, not a stub. A
// market receipt must stay inspectable before confirmation and cannot override
// an off-theme decision.
const price={amount_gbp:12,source:'ebay_browse',label:'Comparable asking prices; not sold prices.',observed_at:'2026-10-24T21:00:00Z',confidence:'matched_listings',
  listings:[{item_id:'fixture-mug',title:'Ceramic mug controlled listing',amount_gbp:12,url:'https://www.ebay.co.uk/itm/123456789012',condition:'Used'}]}
const pricedResponse={...response,fighter:{...response.fighter,combat_profile:{stats:{impact:5,resilience:5,agility:5,control:5},price}}}
const priced=renderToStaticMarkup(createElement(Review,{response:pricedResponse,...props}))
assert.match(priced,/See 1 sourced asking prices/)
assert.match(priced,/Comparable asking prices; not sold prices\./)
assert.match(priced,/href="https:\/\/www\.ebay\.co\.uk\/itm\/123456789012" target="_blank" rel="noopener noreferrer"/)
assert.match(priced,/Ceramic mug controlled listing/)
assert.match(priced,/£12\.00/)
assert.match(priced,/Used/)
assert.match(priced,/<button[^>]*class="review-confirm"[^>]*disabled=""/,'A sourced price cannot override rejected theme eligibility')
const unpriced=renderToStaticMarkup(createElement(Review,{response:{...pricedResponse,fighter:{...pricedResponse.fighter,combat_profile:{...pricedResponse.fighter.combat_profile,price:{amount_gbp:null,source:'unavailable',label:'Marketplace is not configured; neutral price.'}}}},...props}))
assert.match(unpriced,/Marketplace is not configured; neutral price\./)
assert.doesNotMatch(unpriced,/sourced asking prices|ebay\.co\.uk/)

const theme={id:'animals',name:'Animal Kingdom',instructions:'Choose a clear photograph of an animal.',examples:['cat','dog','rabbit','parrot'],rotation_index:4,policy_version:'round-themes-1',enforced:true}
for (const player of [1,2]) {
  const html=renderToStaticMarkup(createElement(CaptureStudio,{player,duration:60,theme,...props,onCancel(){},onPrepare(){throw Error('No requests')}}))
  assert.match(html,/THEME <strong>ANIMAL KINGDOM<\/strong>/)
  assert.match(html,/cat · dog · rabbit · parrot/)
  assert.doesNotMatch(html,/THEME <strong>EVERYDAY OBJECTS/)
}
console.log('Round theme screens passed: both-player saved brief, eligible confirmation, DQ/uncertainty lock, retake and real market receipt component presentation. SSR fixtures only.')
