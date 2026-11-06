"""Authenticated binary envelope. Transport-independent and explicitly versioned."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import struct
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from .codec import BODY_BYTES, pack_text, unpack_text
from ..errors import AuthenticationError, PasscodeError

VERSION = 1
CODEC_ID = 1
PROFILE_ID = 1
HEADER = struct.Struct('>4sBBBB16sI')
MAGIC = b'BIP2'
CHINA_TIME = timezone(timedelta(hours=8))
EPOCH = datetime(2000, 1, 1, tzinfo=CHINA_TIME)
TIME_MODULUS = 100_000_000
ENVELOPE_BYTES = HEADER.size + 2 + BODY_BYTES + 32
AUTH_FAILURE = "无法验证消息：密钥不匹配，或图片数据已损坏、被修改。"

def validate_key(key):
    if not isinstance(key, str) or len(key) != 128 or any(c < '0' or c > '9' for c in key):
        raise PasscodeError("密钥必须是恰好128位半角数字，前导零必须保留。")
    return key

def generate_key():
    return ''.join(secrets.choice('0123456789') for _ in range(128))

def derive_key(key, purpose, nonce=b''):
    validate_key(key)
    return HKDF(algorithm=hashes.SHA256(), length=32,
                salt=nonce if nonce else bytes(16),
                info=b'binary_image_passcode/v1/' + purpose).derive(key.encode('ascii'))

def minute_number(value=None):
    value = datetime.now(CHINA_TIME) if value is None else value
    if value.tzinfo is None:
        value = value.replace(tzinfo=CHINA_TIME)
    delta = value.astimezone(CHINA_TIME) - EPOCH
    minutes = delta.days * 1440 + delta.seconds // 60
    if not 0 <= minutes < TIME_MODULUS:
        raise PasscodeError("生成时间超出范围：北京时间2000-01-01 00:00至2190-02-17 10:39。")
    return minutes

def _offset(key, nonce):
    return int.from_bytes(hmac.digest(derive_key(key, b'time', nonce), b'minutes', 'sha256'), 'big') % TIME_MODULUS

def _mask(key, nonce, minutes, size):
    subkey = derive_key(key, b'body', nonce)
    context = b'mask\x00' + struct.pack('>I', minutes) + nonce
    blocks = (size + 31) // 32
    return b''.join(hmac.digest(subkey, context + i.to_bytes(2, 'big'), 'sha256') for i in range(blocks))[:size]

@dataclass(frozen=True)
class DecodedMessage:
    text: str
    generated_at: datetime
    nonce: bytes
    used_units: int

def seal(text, key, when=None, nonce=None):
    validate_key(key)
    used, body = pack_text(text)
    minutes = minute_number(when)
    nonce = secrets.token_bytes(16) if nonce is None else nonce
    if len(nonce) != 16:
        raise PasscodeError("随机编号长度无效。")
    encrypted_time = (minutes + _offset(key, nonce)) % TIME_MODULUS
    header = HEADER.pack(MAGIC, VERSION, CODEC_ID, PROFILE_ID, 0, nonce, encrypted_time)
    # The body stays exactly 100,000 bits; two encrypted metadata bytes preserve trailing spaces.
    plain = struct.pack('>H', used) + body
    cipher = bytes(a ^ b for a, b in zip(plain, _mask(key, nonce, minutes, len(plain))))
    tag = hmac.digest(derive_key(key, b'authentication', nonce), header + cipher, 'sha256')
    result = header + cipher + tag
    assert len(result) == ENVELOPE_BYTES
    return result

def open_envelope(envelope, key):
    validate_key(key)
    if len(envelope) != ENVELOPE_BYTES:
        raise AuthenticationError(AUTH_FAILURE)
    header, cipher, tag = envelope[:HEADER.size], envelope[HEADER.size:-32], envelope[-32:]
    magic, version, codec, profile, flags, nonce, encrypted_time = HEADER.unpack(header)
    expected = hmac.digest(derive_key(key, b'authentication', nonce), header + cipher, 'sha256')
    if not hmac.compare_digest(tag, expected):
        raise AuthenticationError(AUTH_FAILURE)
    if (magic, version, codec, profile, flags) != (MAGIC, VERSION, CODEC_ID, PROFILE_ID, 0) or encrypted_time >= TIME_MODULUS:
        raise PasscodeError("消息协议版本或字段无效。")
    minutes = (encrypted_time - _offset(key, nonce)) % TIME_MODULUS
    plain = bytes(a ^ b for a, b in zip(cipher, _mask(key, nonce, minutes, len(cipher))))
    used = struct.unpack('>H', plain[:2])[0]
    text = unpack_text(plain[2:], used)
    return DecodedMessage(text, EPOCH + timedelta(minutes=minutes), nonce, used)
