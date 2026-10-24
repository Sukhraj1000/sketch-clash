import { useEffect } from 'react'
import { useThree } from '@react-three/fiber'
import { PMREMGenerator } from 'three'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'

/** Local studio reflections: no remote HDR downloads or changes to island lighting. */
export default function FactoryLighting() {
  const { gl, scene, invalidate } = useThree()
  useEffect(() => {
    const previous = scene.environment
    const intensity = scene.environmentIntensity
    const room = new RoomEnvironment()
    const generator = new PMREMGenerator(gl)
    const reflection = generator.fromScene(room, .04)
    room.dispose()
    generator.dispose()
    scene.environment = reflection.texture
    scene.environmentIntensity = .65
    invalidate()
    return () => {
      scene.environment = previous
      scene.environmentIntensity = intensity
      reflection.dispose()
      invalidate()
    }
  }, [gl, scene, invalidate])
  return <directionalLight position={[5, 6, -5]} color="#BED3E0" intensity={.55} />
}
