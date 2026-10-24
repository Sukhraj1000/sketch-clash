export type ObjectSilhouette = 'pencil' | 'pen' | 'ruler' | 'phone' | 'television' | 'microwave' | 'lamp' | 'battery' | 'shoe' | 'scissors' | 'spoon' | 'keys' | 'pitcher' | 'table' | 'chair' | 'cat' | 'dog' | 'rabbit' | 'bear' | 'duck'

const identities: Record<ObjectSilhouette, readonly string[]> = {
  pencil: ['pencil', 'wooden pencil', 'graphite pencil', 'colored pencil', 'coloured pencil', 'color pencil', 'colour pencil', 'mechanical pencil', 'colouring pencil'],
  pen: ['pen', 'ballpoint pen', 'ballpoint', 'rollerball pen', 'gel pen', 'marker', 'marker pen', 'felt tip pen'],
  ruler: ['ruler', 'measuring ruler', 'plastic ruler', 'wooden ruler', 'metal ruler', 'straightedge', 'straight edge'],
  phone: ['phone', 'mobile phone', 'cell phone', 'cellphone', 'smartphone', 'smart phone'],
  television: ['tv', 'television', 'television set', 'flat screen tv', 'flat screen television', 'smart tv', 'monitor', 'computer monitor', 'desktop monitor', 'display monitor', 'flat screen monitor', 'computer screen'],
  microwave: ['microwave', 'microwave oven', 'countertop microwave', 'countertop microwave oven'],
  lamp: ['lamp', 'desk lamp', 'table lamp', 'reading lamp'],
  battery: ['battery', 'aa battery', 'aaa battery', 'cylindrical battery', 'rechargeable battery'],
  shoe: ['shoe', 'sneaker', 'sneakers', 'trainer', 'trainers', 'running shoe', 'sports shoe'],
  scissors: ['scissors', 'pair of scissors', 'craft scissors', 'paper scissors'],
  spoon: ['spoon', 'teaspoon', 'tablespoon', 'soup spoon', 'wooden spoon'],
  keys: ['key', 'keys', 'house key', 'door key', 'keyring', 'key ring', 'set of keys', 'bunch of keys'],
  pitcher: ['pitcher', 'water pitcher', 'jug', 'water jug', 'measuring jug'],
  table: ['table', 'dining table', 'kitchen table', 'coffee table', 'side table', 'end table', 'wooden table', 'wood table'],
  chair: ['chair', 'dining chair', 'kitchen chair', 'wooden chair', 'wood chair', 'side chair'],
  cat: ['cat', 'kitten', 'toy cat', 'plush cat', 'cat toy figure'],
  dog: ['dog', 'puppy', 'toy dog', 'plush dog', 'dog toy figure'],
  rabbit: ['rabbit', 'bunny', 'toy rabbit', 'plush rabbit'],
  bear: ['teddy bear', 'teddy', 'toy bear', 'plush bear', 'stuffed bear'],
  duck: ['duck', 'rubber duck', 'toy duck', 'duckling'],
}
const normalize = (value?: string) => (value ?? '').normalize('NFKC').trim().toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ')
const lookup = new Map(Object.entries(identities).flatMap(([kind, aliases]) => aliases.map(alias => [alias, kind as ObjectSilhouette])))
const legacyIdentities: Record<string, readonly string[]> = {
  mug: ['mug', 'coffee mug', 'tea mug', 'cup', 'coffee cup', 'teacup'],
  bottle: ['bottle', 'water bottle', 'plastic bottle', 'glass bottle'],
  book: ['book', 'notebook', 'hardback book', 'paperback book', 'textbook'],
  plant: ['plant', 'potted plant', 'houseplant'],
  ball: ['ball', 'football', 'soccer ball', 'basketball', 'tennis ball'],
}
const knownIdentities = new Map<string, string>([...lookup, ...Object.entries(legacyIdentities).flatMap(([kind, aliases]) => aliases.map(alias => [alias, kind] as [string, string]))])

/** A supported furniture noun can have material/colour modifiers and a capture
 * context suffix. The noun must remain the subject: a phone showing a table or
 * a table lamp is never turned into furniture by a substring match. */
function furnitureIdentity(value: string): 'table' | 'chair' | undefined {
  const subject = value.replace(/\s+(?:(?:shown|displayed|pictured|visible)\s+(?:on|in)\s+(?:(?:a|the)\s+)?(?:smartphone|smart phone|mobile phone|phone|computer|tablet)?\s*(?:screen|photograph|photo|picture|image)|in\s+(?:(?:a|the)\s+)?(?:photograph|photo|picture|image))\.?$/, '')
  const match = subject.match(/^(?:(?:a|an|the) )?(?:(?:small|large|simple|rectangular|square|brown|black|white|natural|wooden|wood|oak|pine|timber|solid wood|outdoor) )*(?:(?:dining|kitchen|coffee|side|end) )?(table|chair)$/)
  return match?.[1] as 'table' | 'chair' | undefined
}

/** Accepted identities upgrade coarse legacy geometry; no identity or gameplay data changes. */
export function objectSilhouette(template: string, objectType?: string, canonicalType?: string): ObjectSilhouette | null {
  if (!['generic', 'mug', 'bottle', 'book', 'plant', 'ball'].includes(template)) return null
  const labelKey = normalize(objectType), canonicalKey = normalize(canonicalType)
  const labelFurniture = furnitureIdentity(labelKey), canonicalFurniture = furnitureIdentity(canonicalKey)
  const labelIdentity = knownIdentities.get(labelKey) ?? labelFurniture, canonicalIdentity = knownIdentities.get(canonicalKey) ?? canonicalFurniture
  // Conflicts keep the existing template/photo presentation rather than choosing a convenient identity.
  if (labelIdentity && canonicalIdentity && labelIdentity !== canonicalIdentity) return null
  const label = lookup.get(labelKey) ?? labelFurniture
  const canonical = lookup.get(canonicalKey) ?? canonicalFurniture
  return label ?? canonical ?? null
}
