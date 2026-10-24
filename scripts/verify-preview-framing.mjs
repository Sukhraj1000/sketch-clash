import assert from 'node:assert/strict'
import { PerspectiveCamera, Vector3 } from 'three'
import { previewFraming } from '../src/components/previewFraming.ts'

// Every corner must remain visible through a turntable, including broad tables,
// tall chair backs, large saved scales and portrait/split review viewports.
let samples = 0
for (const [width, height, depth] of [[1.9, 1.2, 1.1], [1.1, 1.8, 1.1], [.8, 1.3, .6], [2.6, 2.8, 1.8]]) {
  const box = { min: { x: -width / 2, y: 0, z: -depth / 2 }, max: { x: width / 2, y: height, z: depth / 2 } }
  for (const aspect of [.55, .85, 1, 1.6, 2.4]) for (const fov of [32, 42]) {
    const frame = previewFraming(box, aspect, fov)
    const camera = new PerspectiveCamera(fov, aspect, .1, 50)
    const center = new Vector3(0, frame.centerY, 0)
    camera.position.copy(new Vector3(.9, .65, 1.8).normalize().multiplyScalar(frame.distance).add(center))
    camera.lookAt(center); camera.updateMatrixWorld()
    for (let angle = 0; angle < Math.PI * 2; angle += Math.PI / 6) {
      for (const x of [box.min.x, box.max.x]) for (const y of [0, height]) for (const z of [box.min.z, box.max.z]) {
        const point = new Vector3(x, y + .08, z).applyAxisAngle(new Vector3(0, 1, 0), angle).project(camera)
        assert.ok(Math.abs(point.x) < .99 && Math.abs(point.y) < .99 && point.z > -1 && point.z < 1, 'Object stays in the preview through rotation')
        samples++
      }
    }
  }
}
console.log(`Preview framing passed: ${samples} projected corners across object shapes, turns and viewports.`)
