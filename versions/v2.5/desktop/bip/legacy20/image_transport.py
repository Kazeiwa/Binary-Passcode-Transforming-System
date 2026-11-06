"""Crop-tolerant tiled RGB parity transport. No dependency on original image dimensions."""
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import hmac
import math
import os
from pathlib import Path
import struct
import tempfile
import threading
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from reedsolo import RSCodec, ReedSolomonError
from .. import erasure
from ..errors import AuthenticationError, PasscodeError, checkpoint
from .protocol import (VERSION, CODEC_ID, PROFILE_ID, ENVELOPE_BYTES, AUTH_FAILURE,
                       derive_key, seal, open_envelope, HEADER as ENVELOPE_HEADER, validate_key)

TILE = 128
MAX_SHARDS = 196
MIN_DATA_SHARDS = 8
MAX_PIXELS = 24_000_000
PACKET = struct.Struct('>4sBBBB16sBBBBHI')
PACKET_MAGIC = b'BIPT'
PARITY_BYTES = 32
PREFIX_BYTES = PACKET.size + PARITY_BYTES
PREFIX_BITS = PREFIX_BYTES * 8
FINDER_SIZE = 14
FINDER_ORIGINS = ((8, 8), (106, 8), (8, 106))
FINDER = np.repeat(np.repeat(np.array([
    [1,1,1,1,1,1,1], [1,0,0,0,0,0,1], [1,0,1,1,1,0,1],
    [1,0,1,1,1,0,1], [1,0,1,1,1,0,1], [1,0,0,0,0,0,1], [1,1,1,1,1,1,1],
], dtype=np.uint8), 2, 0), 2, 1)
_mask = np.ones((TILE, TILE), dtype=bool)
for _x, _y in FINDER_ORIGINS:
    _mask[_y-2:_y+16, _x-2:_x+16] = False
AVAILABLE = np.flatnonzero(_mask.reshape(-1))
AVAILABLE.setflags(write=False)
RS = RSCodec(PARITY_BYTES)
RS_LOCK = threading.RLock()

def coded_length(size):
    return size + PARITY_BYTES * math.ceil(size / (255 - PARITY_BYTES))

@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    margin_x: int
    margin_y: int
    origins: tuple
    n: int
    k: int
    shard_size: int
    selected_fraction: float

@dataclass(frozen=True)
class EncodeResult:
    layout: Layout
    output_path: str
    used_units: int
    message_id: str

@dataclass(frozen=True)
class DecodeResult:
    text: str
    generated_at: object
    message_id: str
    recovered_shards: int
    total_shards: int
    required_shards: int
    corrected_bytes: int
    rotation: int
    used_units: int

def plan_layout(width, height, strength='balanced'):
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS or max(width, height) > 16000:
        raise PasscodeError("图片尺寸无效或过大；最多支持2,400万像素，单边不超过16,000。")
    if strength not in ('balanced', 'strong'):
        raise PasscodeError("未知的冗余配置。")
    mx, my = math.ceil(width * .04), math.ceil(height * .04)
    max_cols, max_rows = (width - 2*mx) // TILE, (height - 2*my) // TILE
    if max_cols < 1 or max_rows < 1:
        raise PasscodeError("图片太窄，无法放置定位块。请使用更大的图片。")
    cols, rows = max_cols, max_rows
    if cols * rows > MAX_SHARDS:
        # Search discrete grids for maximum coverage with a similar aspect ratio.
        candidates = [(c, min(max_rows, MAX_SHARDS // c)) for c in range(1, min(max_cols, MAX_SHARDS)+1)]
        cols, rows = max(candidates, key=lambda cr: (cr[0]*cr[1], -abs(math.log((cr[0]/cr[1])/(width/height)))))
    n = cols * rows
    k = math.ceil(n / (2 if strength == 'balanced' else 3))
    shard_size = math.ceil(ENVELOPE_BYTES / k)
    packet_bits = PREFIX_BITS + coded_length(shard_size + 16) * 8
    if k < MIN_DATA_SHARDS or packet_bits > len(AVAILABLE):
        raise PasscodeError("图片可用面积不足。均衡模式建议至少768×768，增强模式建议至少1024×1024；细长图片需要更大面积。")
    xs = np.rint(np.linspace(mx, width-mx-TILE, cols)).astype(int)
    ys = np.rint(np.linspace(my, height-my-TILE, rows)).astype(int)
    origins = tuple((int(x), int(y)) for y in ys for x in xs)
    fraction = n * (packet_bits + 3 * 18 * 18) / (width * height)
    return Layout(width, height, mx, my, origins, n, k, shard_size, fraction)

def _permutation(pool, seed):
    # SHAKE-derived sort keys produce a deterministic, unique pixel permutation.
    random_words = np.frombuffer(hashlib.shake_256(b'BIP/positions/v1\x00'+seed).digest(len(pool)*8), dtype='>u8')
    return pool[np.argsort(random_words, kind='stable')]

def _header_positions(key):
    order = _permutation(AVAILABLE, derive_key(key, b'header-positions'))
    prefix = order[:PREFIX_BITS]
    remaining = order[PREFIX_BITS:]
    return prefix, remaining

def _body_positions(pool, key, nonce, index, count):
    seed = hmac.digest(derive_key(key, b'body-positions', nonce), bytes([index]), 'sha256')
    return _permutation(pool, seed)[:count]

def _write_bits(tile, positions, bits):
    ys, xs = positions // TILE, positions % TILE
    tile[ys, xs] = (tile[ys, xs] & 254) | bits[:, None]

def _read_bytes(plane, positions):
    bits = plane[positions // TILE, positions % TILE]
    return np.packbits(bits, bitorder='big').tobytes()

def _rs_encode(data):
    with RS_LOCK:
        return bytes(RS.encode(data))

def _rs_decode(data):
    with RS_LOCK:
        decoded, _, errata = RS.decode(data)
    return bytes(decoded), len(errata)

def _packet_header(nonce, index, layout):
    return PACKET.pack(PACKET_MAGIC, VERSION, PROFILE_ID, CODEC_ID, 0,
                       nonce, index, layout.k, layout.n, 0, layout.shard_size, ENVELOPE_BYTES)

def _paint_finders(tile):
    for x, y in FINDER_ORIGINS:
        tile[y-2:y+16, x-2:x+16] &= 254
        tile[y:y+14, x:x+14] |= FINDER[:, :, None]

def load_rgb(path):
    try:
        source = Path(path)
        if source.stat().st_size > 150 * 1024 * 1024:
            raise PasscodeError("图片文件过大。")
        with Image.open(source) as image:
            w, h = image.size
            if w*h > MAX_PIXELS or max(w, h) > 16000:
                raise PasscodeError("图片超过尺寸限制：最多2,400万像素，单边不超过16,000。")
            if getattr(image, 'n_frames', 1) != 1:
                raise PasscodeError("暂不支持动画图片，请先导出静态图片。")
            image = ImageOps.exif_transpose(image)
            if 'A' in image.getbands() or 'transparency' in image.info:
                rgba = image.convert('RGBA')
                white = Image.new('RGBA', rgba.size, 'white')
                image = Image.alpha_composite(white, rgba).convert('RGB')
            else:
                image = image.convert('RGB')
            return np.array(image, dtype=np.uint8, copy=True)
    except PasscodeError:
        raise
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise PasscodeError("无法读取图片，请选择完整的静态PNG或JPEG等常见图片。") from error

def encode_array(rgb, text, key, strength='balanced', when=None, cancel=None, progress=None):
    validate_key(key)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise PasscodeError("图像必须是8位RGB数组。")
    layout = plan_layout(rgb.shape[1], rgb.shape[0], strength)
    checkpoint(cancel)
    envelope = seal(text, key, when)
    nonce = ENVELOPE_HEADER.unpack(envelope[:ENVELOPE_HEADER.size])[-2]
    if progress:
        progress(.03, "正在生成认证数据和裁剪冗余…")
    shards = erasure.encode(envelope, layout.n, layout.k, cancel)
    prefix_positions, pool = _header_positions(key)
    packet_key = derive_key(key, b'packet-authentication', nonce)
    output = np.array(rgb, copy=True)
    for index, ((x, y), shard) in enumerate(zip(layout.origins, shards)):
        checkpoint(cancel)
        header = _packet_header(nonce, index, layout)
        tag = hmac.digest(packet_key, header + shard, 'sha256')[:16]
        prefix = _rs_encode(header)
        body = _rs_encode(shard + tag)
        tile = output[y:y+TILE, x:x+TILE]
        _paint_finders(tile)
        _write_bits(tile, prefix_positions, np.unpackbits(np.frombuffer(prefix, dtype=np.uint8), bitorder='big'))
        bits = np.unpackbits(np.frombuffer(body, dtype=np.uint8), bitorder='big')
        positions = _body_positions(pool, key, nonce, index, len(bits))
        _write_bits(tile, positions, bits)
        if progress:
            progress(.08+.88*(index+1)/layout.n, f"正在写入数据块 {index+1}/{layout.n}…")
    return output, layout, nonce

def encode_file(source, target, text, key, strength='balanced', overwrite=False, cancel=None, progress=None):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise PasscodeError("输出文件不能覆盖原始载体图片，请选择另一个文件名。")
    if target.exists() and not overwrite:
        raise PasscodeError("输出文件已存在，请更换文件名或确认覆盖。")
    if target.suffix.lower() != '.png':
        raise PasscodeError("输出文件必须使用.png扩展名。")
    rgb = load_rgb(source)
    output, layout, nonce = encode_array(rgb, text, key, strength, cancel=cancel, progress=progress)
    checkpoint(cancel)
    from .codec import logical_units
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.bip-', suffix='.png', delete=False) as file:
            temporary = Path(file.name)
        Image.fromarray(output).save(temporary, format='PNG', compress_level=6)
        checkpoint(cancel)
        os.replace(temporary, target)
    except OSError as error:
        raise PasscodeError("无法保存图片，请检查目标目录权限和可用空间。") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    if progress:
        progress(1., "图片已保存。")
    return EncodeResult(layout, str(target), len(logical_units(text)), nonce.hex())

def majority_plane(rgb):
    return (((rgb & 1).sum(axis=2)) >= 2).astype(np.uint8)

def locate_tiles(plane, cancel=None):
    h, w = plane.shape
    if h < TILE or w < TILE:
        return []
    checkpoint(cancel)
    integral = np.zeros((h+1, w+1), dtype=np.uint32)
    integral[1:, 1:] = plane.cumsum(0, dtype=np.uint32).cumsum(1, dtype=np.uint32)
    oh, ow = h-13, w-13
    def window(dy, dx, size):
        y, x = dy, dx
        return (integral[y+size:y+size+oh, x+size:x+size+ow]
                - integral[y:y+oh, x+size:x+size+ow]
                - integral[y+size:y+size+oh, x:x+ow]
                + integral[y:y+oh, x:x+ow]).astype(np.int16)
    mismatch = 132 - window(0, 0, 14) + 2*window(2, 2, 10) - 2*window(4, 4, 6)
    ys, xs = np.where(mismatch <= 12)
    if len(xs) > 6000:
        raise PasscodeError("图片中的候选定位标记过多，无法可靠识别。")
    points = set(zip(xs.tolist(), ys.tolist()))
    origins = set()
    for px, py in points:
        checkpoint(cancel)
        x, y = px-8, py-8
        if x >= 0 and y >= 0 and x+TILE <= w and y+TILE <= h:
            if (x+106, y+8) in points and (x+8, y+106) in points:
                origins.add((x, y))
    return sorted(origins, key=lambda p: (p[1], p[0]))

def _decode_packet(tile, key, prefix_positions, pool):
    prefix, errors = _rs_decode(_read_bytes(tile, prefix_positions))
    if len(prefix) != PACKET.size:
        return None
    magic, version, profile, codec, flags, nonce, index, k, n, reserved, size, total = PACKET.unpack(prefix)
    if (magic, version, profile, codec, flags, reserved) != (PACKET_MAGIC, VERSION, PROFILE_ID, CODEC_ID, 0, 0):
        return None
    if not MIN_DATA_SHARDS <= k <= n <= MAX_SHARDS or index >= n or total != ENVELOPE_BYTES or size != math.ceil(total/k):
        return None
    count = coded_length(size+16)*8
    if count > len(pool):
        return None
    positions = _body_positions(pool, key, nonce, index, count)
    decoded, more_errors = _rs_decode(_read_bytes(tile, positions))
    if len(decoded) != size+16:
        return None
    shard, tag = decoded[:-16], decoded[-16:]
    expected = hmac.digest(derive_key(key, b'packet-authentication', nonce), prefix + shard, 'sha256')[:16]
    if not hmac.compare_digest(tag, expected):
        return None
    return (nonce, k, n, size, total), index, shard, errors + more_errors

def decode_array(rgb, key, cancel=None, progress=None):
    validate_key(key)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise PasscodeError("图像必须是8位RGB数组。")
    if rgb.shape[0]*rgb.shape[1] > MAX_PIXELS:
        raise PasscodeError("图片超过尺寸限制。")
    plane = majority_plane(rgb)
    prefix_positions, pool = _header_positions(key)
    groups = {}
    markers = 0
    seen = set()
    for rotation in range(4):
        checkpoint(cancel)
        oriented = np.rot90(plane, rotation)
        if progress:
            progress(rotation/4+.01, f"正在识别定位点，方向{rotation+1}/4…")
        origins = locate_tiles(oriented, cancel)
        markers += len(origins)
        for j, (x, y) in enumerate(origins):
            checkpoint(cancel)
            try:
                packet = _decode_packet(oriented[y:y+TILE, x:x+TILE], key, prefix_positions, pool)
            except (ReedSolomonError, ValueError, IndexError):
                packet = None
            if packet is not None:
                identity, index, shard, corrected = packet
                if len(groups) >= 32 and identity not in groups:
                    raise PasscodeError("图片包含过多不同的消息。")
                group = groups.setdefault(identity, {'shards': {}, 'errors': 0, 'rotation': rotation})
                if index not in group['shards']:
                    group['shards'][index] = shard
                    group['errors'] += corrected
            if progress:
                progress((rotation+(j+1)/max(1, len(origins)))/4, f"正在校验数据块 {j+1}/{len(origins)}…")
        for identity, group in sorted(groups.items(), key=lambda pair: len(pair[1]['shards']), reverse=True):
            nonce, k, n, size, total = identity
            if len(group['shards']) < k or identity in seen:
                continue
            seen.add(identity)
            envelope = erasure.decode(group['shards'], n, k, total, cancel)
            message = open_envelope(envelope, key)
            if message.nonce != nonce:
                raise AuthenticationError(AUTH_FAILURE)
            if progress:
                progress(1., "消息已通过认证。")
            return DecodeResult(message.text, message.generated_at, nonce.hex(), len(group['shards']), n, k,
                                group['errors'], group['rotation']*90, message.used_units)
    if groups:
        identity, group = max(groups.items(), key=lambda pair: len(pair[1]['shards'])/pair[0][1])
        raise PasscodeError(f"可读数据块不足：找到{len(group['shards'])}/{identity[2]}块，至少需要{identity[1]}块；裁剪或修改超出恢复能力。")
    if markers:
        raise AuthenticationError("已发现定位标记，但无法验证数据：密钥不匹配，或图片数据已损坏、被修改。")
    raise PasscodeError("未找到可识别的消息。请使用原始PNG，确认图片未被缩放、截图或转为JPEG。")

def decode_file(source, key, cancel=None, progress=None):
    return decode_array(load_rgb(source), key, cancel, progress)
