type Bounds = { min: { x: number; y: number; z: number }; max: { x: number; y: number; z: number } }

/** Fit a rotating object, not the display plinth. Sphere padding reserves room
 * for the same small task/idle poses used on the island and narrow viewports. */
export function previewFraming(box: Bounds, aspect: number, verticalFov: number) {
  const centerY = (box.min.y + box.max.y) / 2
  const halfWidth = Math.max(Math.abs(box.min.x), Math.abs(box.max.x))
  const halfDepth = Math.max(Math.abs(box.min.z), Math.abs(box.max.z))
  const halfHeight = (box.max.y - box.min.y) / 2
  const radius = Math.max(.25, Math.hypot(halfWidth, halfDepth, halfHeight) + .13)
  const vertical = verticalFov * Math.PI / 360
  const horizontal = Math.atan(Math.tan(vertical) * Math.max(.1, aspect))
  const distance = radius / Math.sin(Math.min(vertical, horizontal)) * 1.12
  return { centerY, distance, radius }
}
