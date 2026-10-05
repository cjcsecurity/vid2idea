"""Compact source imagery for private storage; untrusted originals stay temporary."""
import base64
import hashlib
import warnings
from io import BytesIO
from PIL import Image, ImageOps


def prepare_image_uploads(images):
    uploads=[]
    for item in images[:3]:
        try:
            if item.path.stat().st_size>4*1024*1024:
                continue
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(item.path) as original:
                    if original.format not in ('JPEG','PNG','WEBP') or original.width*original.height>16_000_000:
                        continue
                    image=ImageOps.exif_transpose(original).convert('RGB')
            image.thumbnail((1280,1280))
            for size in (1280,1024,800,640):
                image.thumbnail((size,size))
                output=BytesIO();image.save(output,format='JPEG',quality=72,optimize=True)
                data=output.getvalue()
                if len(data)<=200*1024:
                    break
            else:
                continue
            uploads.append({'sha256':hashlib.sha256(data).hexdigest(),'data':base64.b64encode(data).decode(),
                            'caption':item.caption,'timestamp_seconds':item.timestamp_seconds})
        except (OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
            continue
    return uploads
