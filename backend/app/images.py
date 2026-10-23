"""Decode once, orient once, bound dimensions, strip metadata, preserve crop coordinates."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from .config import Settings
from .contracts import Crop

# Preserve Pillow decoding before optional ML packages install process-global image plugins.
pillow_open = Image.open

class ImageError(ValueError):
    pass

@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    width: int
    height: int
    mime_type: str = 'image/jpeg'

    @property
    def image_hash(self) -> str:
        return sha256(self.data).hexdigest()

    @property
    def image_ref(self) -> str:
        return f'/api/media/{self.image_hash}'

def encode_image(image: Image.Image) -> ProcessedImage:
    # Flatten transparent input against the game's paper; a crop is never claimed to be segmentation.
    if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
        rgba = image.convert('RGBA')
        rgb = Image.new('RGB', rgba.size, (245, 237, 220))
        rgb.paste(rgba, mask=rgba.getchannel('A'))
    else:
        rgb = image.convert('RGB')
    output = BytesIO()
    rgb.save(output, format='JPEG', quality=88, optimize=True)
    return ProcessedImage(output.getvalue(), *rgb.size)

def normalize_image(data: bytes, mime_type: str, settings: Settings) -> ProcessedImage:
    if mime_type.lower().split(';')[0] not in ('image/jpeg', 'image/png', 'image/webp'):
        raise ImageError('Use a JPEG, PNG or WebP image. Convert HEIC images before uploading.')
    if not data or len(data) > settings.max_upload_bytes:
        raise ImageError(f'Choose an image smaller than {settings.max_upload_bytes // 1024 // 1024} MiB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with pillow_open(BytesIO(data)) as source:
                expected_format = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}[mime_type.lower().split(';')[0]]
                if source.format != expected_format:
                    raise ImageError('The file contents do not match the image type. Export a new JPEG, PNG or WebP.')
                if source.width * source.height > settings.max_image_pixels:
                    raise ImageError('This image exceeds the decoded pixel limit (24 megapixels by default).')
                source.load()
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((settings.inference_max_edge, settings.inference_max_edge), Image.Resampling.LANCZOS)
                return encode_image(oriented)
    except ImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageError('This image could not be decoded. Try another JPEG, PNG or WebP.') from exc

def crop_image(image: ProcessedImage, crop: Crop) -> ProcessedImage:
    if crop.x + crop.width > image.width or crop.y + crop.height > image.height:
        raise ImageError('The crop must stay inside the canonical image dimensions.')
    if crop.width < 16 or crop.height < 16:
        raise ImageError('Select a region at least 16 pixels wide and high.')
    with pillow_open(BytesIO(image.data)) as source:
        return encode_image(source.crop((crop.x, crop.y, crop.x + crop.width, crop.y + crop.height)))
