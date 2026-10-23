import assert from 'node:assert/strict';
// Node 22.18+ native type stripping; these checks need neither a browser nor a camera.
import { clampImageCrop, sniffImageMime, IMAGE_INPUT_LIMITS, cameraFailureMessage, normalizeImage } from '../src/lib/imageInput.ts';

assert.equal(sniffImageMime(Uint8Array.from([255, 216, 255, 219])), 'image/jpeg');
assert.equal(sniffImageMime(Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10])), 'image/png');
assert.equal(sniffImageMime(Buffer.from('RIFF0000WEBP')), 'image/webp');
assert.equal(sniffImageMime(Buffer.from('<svg/>')), null, 'Executable/non-raster formats are unsupported');
assert.deepEqual(clampImageCrop({ x: -10, y: 5, width: 200, height: 200 }, 100, 80), { x: 0, y: 5, width: 100, height: 75 });
assert.equal(clampImageCrop({ x: 0, y: 0, width: 15, height: 20 }, 100, 80), null, 'The frontend uses the backend 16px minimum');
assert.deepEqual(clampImageCrop({ x: 0, y: 0, width: 16, height: 16 }, 100, 80), { x: 0, y: 0, width: 16, height: 16 });
assert.equal(clampImageCrop({ x: NaN, y: 0, width: 20, height: 20 }, 100, 80), null);
assert.equal(clampImageCrop({ x: 90, y: 70, width: 20, height: 20 }, 100, 80), null, 'An undersized clipped crop is rejected');
assert.match(cameraFailureMessage(new DOMException('Denied', 'NotAllowedError')), /upload/, 'Camera denial explains the upload alternative');
await assert.rejects(normalizeImage(new File([Buffer.from('not an image')], 'fake.jpg', { type: 'image/jpeg' })), /JPEG, PNG or WebP/);
await assert.rejects(normalizeImage(new File([Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10])], 'spoof.jpg', { type: 'image/jpeg' })), /do not match/);
await assert.rejects(normalizeImage(new File([new Uint8Array(IMAGE_INPUT_LIMITS.bytes + 1)], 'large.png', { type: 'image/png' })), /larger than 5 MiB/);
const controller = new AbortController();
controller.abort();
await assert.rejects(normalizeImage(new File([], 'empty.png', { type: 'image/png' }), controller.signal), { name: 'AbortError' });

console.log('Image input checks passed: 14 assertions for signatures, MIME mismatch, size limit, cancellation, crop boundaries and camera-denial recovery. Pixel decoding and physical camera capture require browser checks.');
