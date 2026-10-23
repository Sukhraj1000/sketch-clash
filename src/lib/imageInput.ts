export const IMAGE_INPUT_LIMITS = Object.freeze({ bytes: 5 * 1024 * 1024, pixels: 24_000_000, longEdge: 1600 })
export type ImageCrop = { x: number; y: number; width: number; height: number }
export type NormalizedImage = { file: File; width: number; height: number }

function abortIfNeeded(signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException('Image preparation cancelled.', 'AbortError')
}

/** Decode only supported raster formats; browser MIME labels alone are not trustworthy. */
export function sniffImageMime(bytes: Uint8Array): string | null {
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return 'image/jpeg'
  if (bytes.length >= 8 && [137, 80, 78, 71, 13, 10, 26, 10].every((value, i) => bytes[i] === value)) return 'image/png'
  if (bytes.length >= 12 && String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF' && String.fromCharCode(...bytes.slice(8, 12)) === 'WEBP') return 'image/webp'
  return null
}

function canvasFile(canvas: HTMLCanvasElement, name: string): Promise<File> {
  return new Promise((resolve, reject) => canvas.toBlob(blob => {
    if (!blob) return reject(new Error('This browser could not prepare the photograph. Try another image.'))
    if (blob.size > IMAGE_INPUT_LIMITS.bytes) return reject(new Error('The prepared photograph is too large. Please choose a smaller image.'))
    resolve(new File([blob], name, { type: 'image/jpeg' }))
  }, 'image/jpeg', 0.9))
}

function canvasFor(width: number, height: number) {
  if (!width || !height || width * height > IMAGE_INPUT_LIMITS.pixels) throw new Error('Use a photograph no larger than 24 megapixels.')
  const scale = Math.min(1, IMAGE_INPUT_LIMITS.longEdge / Math.max(width, height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width * scale))
  canvas.height = Math.max(1, Math.round(height * scale))
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Photo preparation is unavailable in this browser. Try another browser.')
  context.fillStyle = '#fffcf4'
  context.fillRect(0, 0, canvas.width, canvas.height)
  return { canvas, context }
}

/** EXIF orientation is applied exactly once. Canvas export removes metadata and establishes pixel coordinates. */
export async function normalizeImage(file: File, signal?: AbortSignal): Promise<NormalizedImage> {
  abortIfNeeded(signal)
  if (file.size > IMAGE_INPUT_LIMITS.bytes) throw new Error('This image is larger than 5 MiB. Export a smaller JPEG, PNG or WebP.')
  if (!file.size) throw new Error('This file is empty. Choose a JPEG, PNG or WebP photograph.')
  const supported = ['image/jpeg', 'image/png', 'image/webp']
  const signature = sniffImageMime(new Uint8Array(await file.slice(0, 16).arrayBuffer()))
  abortIfNeeded(signal)
  if (!supported.includes(file.type) || !signature) throw new Error('Use a JPEG, PNG or WebP image. Convert HEIC photos to JPEG first.')
  if (signature !== file.type) throw new Error('The file contents do not match its image type. Export it again as JPEG, PNG or WebP.')
  let bitmap: ImageBitmap
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    throw new Error('This image could not be decoded. Try exporting it as a fresh JPEG, PNG or WebP.')
  }
  try {
    abortIfNeeded(signal)
    const { canvas, context } = canvasFor(bitmap.width, bitmap.height)
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const result = await canvasFile(canvas, 'capture.jpg')
    abortIfNeeded(signal)
    return { file: result, width: canvas.width, height: canvas.height }
  } finally { bitmap.close() }
}

/** The camera preview is never mirrored, so captured and displayed coordinates are identical. */
export async function captureVideoFrame(video: HTMLVideoElement, signal?: AbortSignal): Promise<NormalizedImage> {
  abortIfNeeded(signal)
  if (video.readyState < 2 || !video.videoWidth || !video.videoHeight) throw new Error('The camera is still starting. Wait for the preview, then capture.')
  const { canvas, context } = canvasFor(video.videoWidth, video.videoHeight)
  context.drawImage(video, 0, 0, canvas.width, canvas.height)
  const file = await canvasFile(canvas, 'camera-capture.jpg')
  abortIfNeeded(signal)
  return { file, width: canvas.width, height: canvas.height }
}

/** Clamp to canonical pixel edges; this is not a normalised 0–1 rectangle. */
export function clampImageCrop(crop: ImageCrop, width: number, height: number): ImageCrop | null {
  if (![crop.x, crop.y, crop.width, crop.height, width, height].every(Number.isFinite) || width < 1 || height < 1) return null
  const x = Math.max(0, Math.min(width - 1, Math.round(crop.x)))
  const y = Math.max(0, Math.min(height - 1, Math.round(crop.y)))
  const right = Math.max(x, Math.min(width, Math.round(crop.x + crop.width)))
  const bottom = Math.max(y, Math.min(height, Math.round(crop.y + crop.height)))
  if (right - x < 16 || bottom - y < 16) return null
  return { x, y, width: right - x, height: bottom - y }
}

export function cameraFailureMessage(error: unknown) {
  const name = error instanceof Error ? error.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'Camera permission was not granted. Allow camera access in your browser, or upload a photograph instead.'
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'No usable camera was found. Connect a camera, or upload a photograph instead.'
  if (name === 'NotReadableError' || name === 'AbortError') return 'The camera could not start. Close other apps using it, or upload a photograph instead.'
  return 'Camera access is unavailable here. You can still upload a JPEG, PNG or WebP photograph.'
}
