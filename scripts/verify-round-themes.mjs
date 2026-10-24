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
const { CaptureStudio, captureReviewMessage, captureStatusMessage } = await import(await sourceModule(new URL('../src/components/CaptureStudio.tsx', import.meta.url)))
const response = {capture_id:'saved',status:'recognized',image_url:'/fixture-photo',width:120,height:90,
  fighter:{display_name:'Kiln',object_type:'mug',visual_spec:{},image_ref:'/fixture-photo'},
  theme_validation:{theme_id:'animals',theme_name:'Animal Kingdom',policy_version:'round-themes-1',
    verdict:'outside_theme',reason:'A mug is outside Animal Kingdom. Correct the label or retake.',evidence_labels:['mug'],basis:'recognition_identity_rules'}}
const props = {onFeedback(){throw Error('No writes')},onCorrect(){throw Error('No writes')},onRevised(){},onConfirm(){throw Error('No writes')},onRetake(){}}
const staleSuccess='Object recognised. Fighter checked. Ready to battle.'
const disqualifiedStatus=captureStatusMessage('recognized',response,staleSuccess)
assert.match(disqualifiedStatus,/Capture disqualified for this round/)
assert.match(disqualifiedStatus,/Correct the label or retake/)
assert.doesNotMatch(disqualifiedStatus,/Ready to battle/,'A stale success message cannot contradict capture DQ')
const unclearResponse={...response,theme_validation:{...response.theme_validation,verdict:'uncertain',reason:'Correct the identity or use a clearer photograph.'}}
const uncertainStatus=captureStatusMessage('recognized',unclearResponse,staleSuccess)
assert.match(uncertainStatus,/Theme eligibility is not confirmed/)
assert.match(uncertainStatus,/Correct the identity or use a clearer photograph/)
assert.doesNotMatch(uncertainStatus,/disqualified|Ready to battle/)
// A detector-only doubt asks the player to confirm instead of naming the detector's guess.
const doubtStatus=captureStatusMessage('recognized',{...unclearResponse,theme_validation:{...unclearResponse.theme_validation,resolution:'confirm_identity'}},staleSuccess)
assert.match(doubtStatus,/choose Correct to lock it in/)
assert.doesNotMatch(doubtStatus,/detector|YOLO|not confirmed/)
assert.equal(captureStatusMessage('processing',response,'Checking revised photograph…'),'Checking revised photograph…')
assert.equal(captureStatusMessage('error',response,'Upload failed. Retry.'),'Upload failed. Retry.')
assert.match(captureReviewMessage({theme_validation:{...response.theme_validation,verdict:'eligible'}}),/Review the identity and fighter before locking it in/)
assert.doesNotMatch(captureReviewMessage({degraded:true}),/Ready to battle/)
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

// Keep player decisions ahead of optional detail, without hiding disagreement
// or changing the explicit feedback/evaluation choices.
const reviewable = renderToStaticMarkup(createElement(Review,{response:{...response,output_id:'output-1',pipeline_version_id:'review-v1',
  evidence:{identity_support:{detail:'YOLO suggested person; Gemini proposed table. Check the photograph.'}},
  theme_validation:{...response.theme_validation,verdict:'eligible'}},...props}))
assert.ok(reviewable.indexOf('YOUR PHOTOGRAPH') < reviewable.indexOf('Is this your object?'))
assert.ok(reviewable.indexOf('Lock in my fighter') < reviewable.indexOf('Battle attributes &amp; evidence'),'Confirm must precede optional evidence in reading order')
assert.match(reviewable,/<details class="review-evidence">/,'Evidence starts collapsed')
assert.doesNotMatch(reviewable,/<details class="review-evidence"[^>]*open/)
assert.ok(reviewable.indexOf('YOLO suggested person') < reviewable.indexOf('<details'),'Detector disagreement must remain outside collapsed evidence')
assert.match(reviewable,/<button[^>]*class="review-confirm"[^>]*disabled=""/,'Fresh proposals still need an explicit identity confirmation')
assert.doesNotMatch(reviewable,/<input[^>]*checked=""/,'Optional shared evaluation must remain off')
assert.match(reviewable,/Check the photograph and choose Correct to continue/)
assert.match(reviewable,/Allow this object photo and feedback/)
assert.match(reviewable,/Shared evaluation is off/)

// Pricing integration renders its real component recursively, not a stub. A
// market receipt must stay inspectable before confirmation and cannot override
// an off-theme decision.
const price={amount_gbp:12,source:'retailer_page',label:'Comparable UK retail prices from retailer pages.',observed_at:'2026-10-24T21:00:00Z',confidence:'retail_reference',
  cache:{hit:true,persistence:'mongodb',stored_at:'2026-10-24T21:01:00Z',expires_at:'2026-10-31T21:01:00Z',snapshot_id:'saved-quote'},
  listings:[{item_id:'fixture-mug',title:'Ceramic mug controlled listing',amount_gbp:12,url:'https://shop.example/mug',condition:'New',retailer:'Example Shop',checked_at:'2026-10-24T21:00:00Z'}]}
const pricedResponse={...response,fighter:{...response.fighter,combat_profile:{stats:{impact:5,resilience:5,agility:5,control:5},price}}}
const priced=renderToStaticMarkup(createElement(Review,{response:pricedResponse,...props}))
assert.match(priced,/Retailer page reference/)
assert.match(priced,/1 saved price reference/)
assert.match(priced,/Comparable UK retail prices from retailer pages\./)
assert.match(priced,/href="https:\/\/shop\.example\/mug" target="_blank" rel="noopener noreferrer"/)
assert.match(priced,/Ceramic mug controlled listing/)
assert.match(priced,/£12\.00/)
assert.match(priced,/Example Shop · New/)
assert.match(priced,/Cache hit · MongoDB Atlas/)
assert.match(priced,/24 Oct 2026/)
assert.match(priced,/Cache refresh due/)
assert.match(priced,/Price adds at most 1% to damage; unknown prices are neutral/)
assert.doesNotMatch(priced,/verified appraisal|eBay|Checked retail reference/)
assert.match(priced,/<button[^>]*class="review-confirm"[^>]*disabled=""/,'A sourced price cannot override rejected theme eligibility')
const renderPrice=price=>renderToStaticMarkup(createElement(Review,{response:{...pricedResponse,fighter:{...pricedResponse.fighter,combat_profile:{...pricedResponse.fighter.combat_profile,price}}},...props}))
const starter=renderPrice({...price,source:'curated_retail',cache:{...price.cache,hit:false},label:'Manually checked UK retail reference.'})
assert.match(starter,/Checked retail reference/)
assert.match(starter,/Sourced starter · MongoDB Atlas/)
assert.doesNotMatch(starter,/Retailer page reference/)
const memory=renderPrice({...price,cache:{...price.cache,hit:true,persistence:'development_memory'}})
assert.match(memory,/Cache hit · temporary cache/)
assert.doesNotMatch(memory,/Cache hit · MongoDB Atlas/)
const unpriced=renderPrice({...price,amount_gbp:null,source:'unavailable',label:'No matching sourced retail price; neutral price.'})
assert.match(unpriced,/No sourced price · neutral/)
assert.match(unpriced,/No matching sourced retail price; neutral price\./)
assert.match(unpriced,/If either object has no price, both price bonuses are zero/)
assert.doesNotMatch(unpriced,/saved price reference|shop\.example|Retailer page reference|Cache hit/,'Unknown prices never expose stale priced receipts')
const unsafe=renderPrice({...price,listings:[
  {...price.listings[0],item_id:'script',url:'javascript:alert(1)',title:'<img src=x onerror=alert(1)>'},
  {...price.listings[0],item_id:'credentials',url:'https://user:secret@shop.example/private'},
]})
assert.doesNotMatch(unsafe,/href="(?:javascript:|data:|http:|https:\/\/user:)/)
assert.doesNotMatch(unsafe,/<script>|<img src="x"/,'Source titles render as text only')
assert.match(unsafe,/&lt;img src=x onerror=alert\(1\)&gt;/)
const {safePriceSourceUrl}=await import(await sourceModule(new URL('../src/components/MarketPriceEvidence.tsx',import.meta.url)))
for (const url of ['javascript:alert(1)','data:text/html,unsafe','//shop.example/item','http://shop.example/item','https://user:secret@shop.example/item','not a url']) assert.equal(safePriceSourceUrl(url),undefined)
assert.equal(safePriceSourceUrl('https://shop.example/item?q=mug'),'https://shop.example/item?q=mug')

const theme={id:'animals',name:'Animal Kingdom',instructions:'Choose a clear photograph of an animal.',examples:['cat','dog','rabbit','parrot'],rotation_index:4,policy_version:'round-themes-1',enforced:true}
for (const player of [1,2]) {
  const html=renderToStaticMarkup(createElement(CaptureStudio,{player,duration:60,theme,...props,onCancel(){},onPrepare(){throw Error('No requests')}}))
  assert.match(html,/THEME <strong>ANIMAL KINGDOM<\/strong>/)
  assert.match(html,/cat · dog · rabbit · parrot/)
  assert.doesNotMatch(html,/THEME <strong>EVERYDAY OBJECTS/)
}
console.log('Round theme screens passed: both-player saved brief, eligible confirmation, DQ/uncertainty lock, retake and real market receipt component presentation. SSR fixtures only.')
