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
from .errors import AuthenticationError, PasscodeError

VERSION = 2
CODEC_ID = 1
PROFILE_ID = 2
NONCE_BYTES = 48
TIME_BYTES = 5
HEADER = struct.Struct('>4sBBBB48s5s')
MAGIC = b'BIP2'
CHINA_TIME = timezone(timedelta(hours=8))
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
TIME_MODULUS = 10_000_000_000
TIME_LAST = EPOCH + timedelta(seconds=TIME_MODULUS - 1)
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
                info=b'binary_image_passcode/v2.1/' + purpose).derive(key.encode('ascii'))

def second_number(value=None):
    value = datetime.now(timezone.utc) if value is None else value
    if value.tzinfo is None:
        value = value.replace(tzinfo=CHINA_TIME)
    delta = value.astimezone(timezone.utc) - EPOCH
    seconds = delta.days * 86400 + delta.seconds
    if not 0 <= seconds < TIME_MODULUS:
        raise PasscodeError("生成时间超出10位秒数范围：UTC 1970-01-01 00:00:00至" + TIME_LAST.strftime('%Y-%m-%d %H:%M:%S') + "。")
    return seconds

def _offset(key, nonce):
    return int.from_bytes(hmac.digest(derive_key(key, b'time', nonce), b'seconds', 'sha256'), 'big') % TIME_MODULUS

def _mask(key, nonce, seconds, size):
    subkey = derive_key(key, b'body', nonce)
    context = b'mask\x00' + seconds.to_bytes(TIME_BYTES, 'big') + nonce
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
    seconds = second_number(when)
    nonce = secrets.token_bytes(NONCE_BYTES) if nonce is None else nonce
    if not isinstance(nonce, bytes) or len(nonce) != NONCE_BYTES:
        raise PasscodeError("随机编号长度无效。")
    encrypted_time = (seconds + _offset(key, nonce)) % TIME_MODULUS
    header = HEADER.pack(MAGIC, VERSION, CODEC_ID, PROFILE_ID, 0, nonce, encrypted_time.to_bytes(TIME_BYTES, 'big'))
    # The body stays exactly 300,000 bits; two encrypted metadata bytes preserve trailing spaces.
    plain = struct.pack('>H', used) + body
    cipher = bytes(a ^ b for a, b in zip(plain, _mask(key, nonce, seconds, len(plain))))
    tag = hmac.digest(derive_key(key, b'authentication', nonce), header + cipher, 'sha256')
    result = header + cipher + tag
    assert len(result) == ENVELOPE_BYTES
    return result

def open_envelope(envelope, key):
    validate_key(key)
    if len(envelope) != ENVELOPE_BYTES:
        raise AuthenticationError(AUTH_FAILURE)
    header, cipher, tag = envelope[:HEADER.size], envelope[HEADER.size:-32], envelope[-32:]
    magic, version, codec, profile, flags, nonce, time_bytes = HEADER.unpack(header)
    expected = hmac.digest(derive_key(key, b'authentication', nonce), header + cipher, 'sha256')
    if not hmac.compare_digest(tag, expected):
        raise AuthenticationError(AUTH_FAILURE)
    encrypted_time = int.from_bytes(time_bytes, 'big')
    if (magic, version, codec, profile, flags) != (MAGIC, VERSION, CODEC_ID, PROFILE_ID, 0) or encrypted_time >= TIME_MODULUS:
        raise PasscodeError("消息协议版本或字段无效。")
    seconds = (encrypted_time - _offset(key, nonce)) % TIME_MODULUS
    plain = bytes(a ^ b for a, b in zip(cipher, _mask(key, nonce, seconds, len(cipher))))
    used = struct.unpack('>H', plain[:2])[0]
    text = unpack_text(plain[2:], used)
    return DecodedMessage(text, (EPOCH + timedelta(seconds=seconds)).astimezone(CHINA_TIME), nonce, used)
