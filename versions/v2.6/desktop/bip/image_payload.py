"""JPEG messages for V2.5. Independent authenticated payload over the tiled transport."""
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from pathlib import Path
import hashlib
import hmac
import math
import secrets
import struct
import warnings
from contextlib import contextmanager
from PIL import Image, ImageOps, UnidentifiedImageError
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from .errors import PasscodeError, AuthenticationError, checkpoint
from .protocol import (HEADER, EPOCH, CHINA_TIME, TIME_MODULUS, AUTH_FAILURE,
                       second_number, validate_key, NONCE_BYTES)

WIRE = (3, 3, 2)  # packet version, profile, codec; text keeps its original profile.
META = struct.Struct('>HHBBI')
MAX_JPEG_BYTES = 512_000
MAX_PNG_BYTES = 9_000_000
MAX_SECRET_PIXELS = 1920 * 1080
OVERHEAD = HEADER.size + META.size + 16
MAX_ENVELOPE = MAX_PNG_BYTES + OVERHEAD

@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    width: int
    height: int
    quality: int
    original_size: tuple
    format: str = 'JPEG'

@dataclass(frozen=True)
class ImageMessage:
    image: PreparedImage
    generated_at: object
    nonce: bytes

@dataclass(frozen=True)
class ImageEncodeResult:
    layout: object
    output_path: str
    image: PreparedImage
    message_id: str

def _derive(key, purpose, nonce):
    validate_key(key)
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=nonce,
                info=b'binary_image_passcode/v2.5/' + purpose).derive(key.encode('ascii'))

def _offset(key, nonce):
    return int.from_bytes(hmac.digest(_derive(key, b'image-time', nonce), b'seconds', 'sha256'), 'big') % TIME_MODULUS

def _iv(key, nonce):
    return hmac.digest(_derive(key, b'image-iv', nonce), b'jpeg', 'sha256')[:12]

def _validate_jpeg(data, width, height, format='JPEG'):
    if (not 1 <= len(data) <= (MAX_PNG_BYTES if format == 'PNG' else MAX_JPEG_BYTES) or not 1 <= width or not 1 <= height
            or max(width, height) > 1920 or min(width, height) > 1080
            or width * height > MAX_SECRET_PIXELS):
        raise PasscodeError('图片正文尺寸或长度无效。')
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != format or image.size != (width, height) or image.mode not in (('RGB','RGBA') if format=='PNG' else ('RGB',)):
                raise PasscodeError('图片正文格式、尺寸或颜色模式无效。')
            image.load()
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise PasscodeError('图片正文已损坏，无法读取。') from error

def seal_image(image, key, when=None, nonce=None):
    validate_key(key)
    _validate_jpeg(image.data, image.width, image.height, image.format)
    if image.format not in ('JPEG','PNG') or not (image.quality == 0 if image.format == 'PNG' else 50 <= image.quality <= 85):
        raise PasscodeError('图片压缩参数无效。')
    nonce = secrets.token_bytes(NONCE_BYTES) if nonce is None else nonce
    if not isinstance(nonce, bytes) or len(nonce) != NONCE_BYTES:
        raise PasscodeError('随机编号长度无效。')
    seconds = second_number(when)
    header = HEADER.pack(b'BIP3', 3, 2, 3, 0, nonce,
                         ((seconds + _offset(key, nonce)) % TIME_MODULUS).to_bytes(5, 'big'))
    plain = META.pack(image.width, image.height, image.quality, 2 if image.format == 'PNG' else 1, len(image.data)) + image.data
    return header + AESGCM(_derive(key, b'image-body', nonce)).encrypt(_iv(key, nonce), plain, header)

def open_image(envelope, key):
    validate_key(key)
    if not OVERHEAD < len(envelope) <= MAX_ENVELOPE:
        raise AuthenticationError(AUTH_FAILURE)
    header = envelope[:HEADER.size]
    magic, version, codec, profile, flags, nonce, encrypted = HEADER.unpack(header)
    try:
        plain = AESGCM(_derive(key, b'image-body', nonce)).decrypt(_iv(key, nonce), envelope[HEADER.size:], header)
    except InvalidTag:
        raise AuthenticationError(AUTH_FAILURE) from None
    value = int.from_bytes(encrypted, 'big')
    if (magic, version, codec, profile, flags) != (b'BIP3', 3, 2, 3, 0) or value >= TIME_MODULUS:
        raise PasscodeError('图片消息格式无效。')
    width, height, quality, kind, size = META.unpack(plain[:META.size])
    data = plain[META.size:]
    if kind not in (1,2) or size != len(data) or not (quality == 0 if kind==2 else 50 <= quality <= 85):
        raise PasscodeError('图片消息参数无效。')
    format = 'PNG' if kind==2 else 'JPEG'
    _validate_jpeg(data, width, height, format)
    seconds = (value - _offset(key, nonce)) % TIME_MODULUS
    return ImageMessage(PreparedImage(data, width, height, quality, (width, height), format),
                        (EPOCH + timedelta(seconds=seconds)).astimezone(CHINA_TIME), nonce)

def jpeg_capacity(width, height, strength='balanced'):
    from .image_transport import plan_layout, AVAILABLE, PREFIX_BITS, coded_length
    plan = plan_layout(width, height, strength, envelope_bytes=OVERHEAD+1)
    # Preserve both RS protection and the selected outer erasure threshold.
    max_shard = max(s for s in range(1, len(AVAILABLE)//8)
                    if PREFIX_BITS + coded_length(s+16)*8 <= len(AVAILABLE))
    return min(MAX_JPEG_BYTES, plan.k * max_shard - OVERHEAD)

def _memory_budget():
    """Best-effort physical-memory budget, not a source-resolution policy."""
    try:
        import os
        if os.name == 'nt':
            import ctypes
            class Status(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in ('total', 'available', 'page', 'free_page', 'virtual', 'free_virtual', 'extended')]
            value = Status(); value.length = ctypes.sizeof(value)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
                return int(value.available * .6)
        else:
            return int(os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') * .6)
    except (AttributeError, OSError, ValueError):
        pass
    return None

@contextmanager
def _open_secret(source):
    # Only opening the header needs the generic Pillow pixel threshold disabled.
    # Carrier validation keeps its explicit bounds; secret decoding is memory-checked.
    previous = Image.MAX_IMAGE_PIXELS
    try:
        Image.MAX_IMAGE_PIXELS = None
        image = Image.open(source)
    finally:
        Image.MAX_IMAGE_PIXELS = previous
    try:
        yield image
    finally:
        image.close()

def prepare_image(source, max_bytes=None, cancel=None, progress=None, lossless=False):
    maximum=MAX_PNG_BYTES if lossless else MAX_JPEG_BYTES
    max_bytes=maximum if max_bytes is None else min(maximum,int(max_bytes))
    if max_bytes < 2048:
        raise PasscodeError('载体可用空间不足，请选择更大的载体图片。')
    try:
        source = Path(source)
        if source.stat().st_size > 150 * 1024 * 1024:
            raise PasscodeError('待加密图片超过150MiB，请先缩小文件。')
        with _open_secret(source) as original:
            if getattr(original, 'n_frames', 1) != 1:
                raise PasscodeError('请选择静态图片；动画或多页图片请先导出其中一张。')
            checkpoint(cancel)
            orientation = original.getexif().get(274, 1)
            swapped = orientation in (5, 6, 7, 8)
            original_size = original.size[::-1] if swapped else original.size
            box = (1920, 1080) if original_size[0] >= original_size[1] else (1080, 1920)
            decoder_box = box[::-1] if swapped else box
            original.draft('RGB', decoder_box)  # JPEG can decode at reduced resolution.
            budget = _memory_budget()
            if budget is not None and original.width * original.height * 12 > budget:
                raise PasscodeError('当前可用内存不足以读取这张图片，请关闭其他程序后重试，或先转为JPG再选择。')
            original.thumbnail(decoder_box, Image.Resampling.LANCZOS)
            image = ImageOps.exif_transpose(original)
            if 'A' in image.getbands() or 'transparency' in image.info:
                rgba = image.convert('RGBA')
                image = rgba.copy() if lossless else Image.alpha_composite(Image.new('RGBA', rgba.size, 'white'), rgba).convert('RGB')
            else:
                image = image.convert('RGB')
    except MemoryError as error:
        raise PasscodeError('当前内存不足以处理这张图片，请关闭其他程序后重试。') from error
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise PasscodeError('无法读取待加密图片，请选择完整的PNG、JPG、BMP、WebP、TIFF等静态图片。') from error
    if lossless:
        checkpoint(cancel)
        buffer = BytesIO();image.save(buffer,format='PNG',compress_level=9)
        data=buffer.getvalue()
        if len(data)>max_bytes:
            from .dense_transport import square_required
            required=square_required(len(data))
            hint=f'建议底图至少{required[0]}×{required[1]}像素。' if required else '请减少图片内容或改用JPG模式。'
            raise PasscodeError(f'PNG无损图片需要{len(data)/1024:.1f} KiB，当前底图可用{max_bytes/1024:.1f} KiB。'+hint+'无损模式不会继续缩小或降低画质。')
        return PreparedImage(data,image.width,image.height,0,original_size,'PNG')
    while True:
        for quality in range(85, 49, -5):
            checkpoint(cancel)
            if progress:
                progress(.01, f'正在压缩图片：{image.width}×{image.height}…')
            buffer = BytesIO()
            image.save(buffer, format='JPEG', quality=quality, optimize=True, subsampling=2)
            data = buffer.getvalue()
            if len(data) <= max_bytes:
                return PreparedImage(data, image.width, image.height, quality, original_size)
        if image.size == (1, 1):
            raise PasscodeError('图片无法压缩到载体容量内，请选择更大的载体。')
        image = image.resize((max(1, int(image.width*.85)), max(1, int(image.height*.85))), Image.Resampling.LANCZOS)

def encode_image_file(carrier, target, secret, key, strength='balanced', overwrite=False,
                      cancel=None, progress=None, when=None, lossless=False):
    from .image_transport import load_rgb, encode_array, save_png
    carrier, target, secret = Path(carrier), Path(target), Path(secret)
    if target.resolve() in (carrier.resolve(), secret.resolve()):
        raise PasscodeError('输出不能覆盖载体或待加密的原始图片，请另选文件名。')
    if target.exists() and not overwrite:
        raise PasscodeError('输出文件已存在，请更换文件名或确认覆盖。')
    if target.suffix.lower() != '.png':
        raise PasscodeError('加密后的载体必须保存为PNG；解密后可保存为JPG。')
    validate_key(key)
    rgb = load_rgb(carrier)
    if lossless:
        from .dense_transport import capacity
        limit=capacity(rgb.shape[1],rgb.shape[0])
    else:
        limit=jpeg_capacity(rgb.shape[1],rgb.shape[0],strength)
    image = prepare_image(secret, limit, cancel, progress, lossless=lossless)
    envelope = seal_image(image, key, when)
    checkpoint(cancel)
    if lossless:
        from .dense_transport import encode
        output,layout,nonce=encode(rgb,envelope,key,cancel,progress)
    else:
        output, layout, nonce = encode_array(rgb, '', key, strength, cancel=cancel, progress=progress, _envelope=envelope)
    save_png(output, target, cancel)
    if progress:
        progress(1., '图片消息已保存。')
    return ImageEncodeResult(layout, str(target), image, nonce.hex())

def save_image_result(result, target, overwrite=False, protected_paths=()):
    from .vault import atomic_write
    target = Path(target)
    if not result.image_bytes:
        raise PasscodeError('当前结果不是图片消息。')
    allowed=('.png',) if result.image_format=='PNG' else ('.jpg','.jpeg')
    if target.suffix.lower() not in allowed:
        raise PasscodeError('无损图片请保存为.png文件。' if result.image_format=='PNG' else '解密图片请保存为.jpg或.jpeg文件。')
    if any(target.resolve() == Path(p).resolve() for p in protected_paths if p):
        raise PasscodeError('解密输出不能覆盖原始图片，请另选文件名。')
    if target.exists() and not overwrite:
        raise PasscodeError('目标文件已存在，请确认覆盖或另选文件名。')
    atomic_write(target, result.image_bytes)
