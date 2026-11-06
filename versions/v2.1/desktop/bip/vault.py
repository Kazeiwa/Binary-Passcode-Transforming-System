"""Encrypted multi-key vault; Windows DPAPI, Linux Secret Service, or a master password."""
import base64
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from .errors import PasscodeError
from .protocol import generate_key, validate_key

MAX_VAULT_BYTES = 2_000_000
MAX_KEYS = 256

def app_data_dir():
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'BinaryImagePasscode'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'binary_image_passcode'

def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.bip-', delete=False) as handle:
            temporary = Path(handle.name)
            if os.name != 'nt':
                os.fchmod(handle.fileno(), 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise PasscodeError("保存失败，请检查目录权限及可用空间。") from error
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)

@contextmanager
def _file_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    acquired = False
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b'0')
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            raise PasscodeError("另一个窗口正在保存密钥库，请稍后重试。") from None
        yield
    finally:
        if acquired:
            if os.name == 'nt':
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

def _b64(data):
    return base64.b64encode(data).decode('ascii')

def _unb64(data, length=None):
    try:
        result = base64.b64decode(data, validate=True)
        if length is not None and len(result) != length:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise PasscodeError("加密存储格式损坏。") from None

def _json(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')

def _parse(raw):
    if len(raw) > MAX_VAULT_BYTES:
        raise PasscodeError("密钥文件过大。")
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (ValueError, TypeError, UnicodeError):
        raise PasscodeError("密钥文件格式损坏。") from None

def _password_key(password, salt):
    if not isinstance(password, str) or len(password) < 12:
        raise PasscodeError("主密码至少需要12个字符，请使用不易猜测的密码。")
    if len(password) > 1024:
        raise PasscodeError("主密码过长。")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode('utf-8'))

def _dpapi(data, decrypt=False):
    if os.name != 'nt':
        raise PasscodeError("此密钥库属于Windows账户，无法在当前系统直接解锁；请导入加密备份。")
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    pointer = ctypes.POINTER(Blob)
    crypt.CryptProtectData.argtypes = [pointer, wintypes.LPCWSTR, pointer, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, pointer]
    crypt.CryptUnprotectData.argtypes = [pointer, ctypes.POINTER(wintypes.LPWSTR), pointer, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, pointer]
    crypt.CryptProtectData.restype = crypt.CryptUnprotectData.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    ok = (crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)) if decrypt
          else crypt.CryptProtectData(ctypes.byref(source), 'Binary Image Passcode vault', None, None, None, 1, ctypes.byref(result)))
    if not ok:
        raise PasscodeError("Windows账户保护无法解锁密钥库；请使用原账户，或导入加密备份。")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel.LocalFree(result.pbData)

def _secret_service(vault_id, secret=None):
    arguments = ['secret-tool', 'lookup' if secret is None else 'store']
    if secret is not None:
        arguments += ['--label=Binary Image Passcode vault']
    arguments += ['application', 'binary_image_passcode', 'vault', vault_id]
    try:
        result = subprocess.run(arguments, input='' if secret is None else secret.hex()+'\n',
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as error:
        raise PasscodeError("无法访问系统密钥环。请安装libsecret-tools并解锁桌面密钥环，或使用主密码保护。") from error
    if result.returncode != 0:
        raise PasscodeError("系统密钥环读取或保存失败，请确认桌面会话及密钥环已解锁。")
    if secret is None:
        try:
            value = bytes.fromhex(result.stdout.strip())
            if len(value) != 32:
                raise ValueError()
            return value
        except ValueError:
            raise PasscodeError("系统密钥环中的保护信息无效，请导入加密备份。") from None

def _system_mode():
    if os.name == 'nt':
        return 'windows'
    if sys.platform.startswith('linux'):
        return 'linux'
    raise PasscodeError("当前系统请使用主密码保护。")

def _name(name):
    name = str(name).strip()
    if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise PasscodeError("密钥名称应为1—80个可见字符。")
    return name

def _validate_data(data):
    if not isinstance(data, dict) or not isinstance(data.get('keys'), list) or len(data['keys']) > MAX_KEYS:
        raise PasscodeError("密钥库记录无效或数量超过256。")
    ids, names, secrets_seen = set(), set(), set()
    for item in data['keys']:
        if not isinstance(item, dict):
            raise PasscodeError("密钥记录无效。")
        identity = item.get('id')
        if not isinstance(identity, str) or len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
            raise PasscodeError("密钥标识无效。")
        name = _name(item.get('name', ''))
        key = validate_key(item.get('key'))
        if identity in ids or name in names or key in secrets_seen:
            raise PasscodeError("密钥库存在重复记录。")
        if not isinstance(item.get('created'), str) or len(item['created']) > 40:
            raise PasscodeError("密钥记录日期无效。")
        ids.add(identity); names.add(name); secrets_seen.add(key)
    if data.get('default') is not None and data['default'] not in ids:
        raise PasscodeError("默认密钥记录无效。")
    return data

class KeyVault:
    def __init__(self, path=None):
        self.path = Path(path) if path else app_data_dir() / 'vault.bipvault'
        self._master = self._data = self._meta = self._revision = None
        self._lock = threading.RLock()

    @property
    def exists(self):
        return self.path.exists()

    @property
    def locked(self):
        return self._master is None or self._data is None

    @property
    def mode(self):
        return self._read()[0].get('mode') if self.exists else None

    def _read(self):
        try:
            if self.path.stat().st_size > MAX_VAULT_BYTES:
                raise PasscodeError("密钥库文件过大。")
            raw = self.path.read_bytes()
            data = _parse(raw)
        except OSError as error:
            raise PasscodeError("无法读取密钥库文件。") from error
        identity = data.get('id', '')
        if (data.get('format'), data.get('version')) != ('BIP-VAULT', 1) or not isinstance(identity, str) or len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
            raise PasscodeError("密钥库格式不受支持或已损坏。")
        if data.get('mode') not in ('windows', 'linux', 'password'):
            raise PasscodeError("密钥库保护方式无效。")
        if any(not isinstance(data.get(k), str) for k in ('protection', 'nonce', 'ciphertext')):
            raise PasscodeError("密钥库字段不完整。")
        return data, hashlib.sha256(raw).digest()

    def _require(self):
        if self.locked:
            raise PasscodeError("密钥库已锁定，请先解锁。")

    def create(self, mode='system', password=None):
        with self._lock:
            if self.exists:
                raise PasscodeError("密钥库已存在，请解锁现有密钥库。")
            identity = secrets.token_hex(16)
            meta = {'format': 'BIP-VAULT', 'version': 1, 'id': identity}
            master = secrets.token_bytes(32)
            if mode == 'password':
                salt = secrets.token_bytes(16)
                master = _password_key(password, salt)
                meta.update(mode='password', protection=_b64(salt))
            elif mode == 'system':
                backend = _system_mode()
                if backend == 'windows':
                    meta.update(mode='windows', protection=_b64(_dpapi(master)))
                else:
                    _secret_service(identity, master)
                    meta.update(mode='linux', protection='secret-service')
            else:
                raise PasscodeError("当前系统请使用主密码保护。")
            self._meta, self._master = meta, master
            try:
                self._commit({'keys': [], 'default': None})
            except Exception:
                self.lock()
                raise

    def unlock(self, password=None):
        with self._lock:
            self.lock()
            raw, revision = self._read()
            nonce, cipher = _unb64(raw.get('nonce'), 12), _unb64(raw.get('ciphertext'))
            meta = {k: raw[k] for k in ('format', 'version', 'id', 'mode', 'protection')}
            if meta['mode'] == 'password':
                master = _password_key(password, _unb64(meta['protection'], 16))
            elif meta['mode'] == 'windows':
                master = _dpapi(_unb64(meta['protection']), True)
            else:
                master = _secret_service(meta['id'])
            if len(master) != 32:
                raise PasscodeError("密钥库保护信息无效。")
            try:
                data = _validate_data(_parse(AESGCM(master).decrypt(nonce, cipher, _json(meta))))
            except InvalidTag:
                raise PasscodeError("无法解锁：主密码不正确，或密钥库已损坏。") from None
            self._meta, self._master, self._data, self._revision = meta, master, data, revision

    def lock(self):
        with self._lock:
            self._master = self._data = self._meta = self._revision = None

    def _commit(self, data):
        _validate_data(data)
        nonce = secrets.token_bytes(12)
        encrypted = AESGCM(self._master).encrypt(nonce, _json(data), _json(self._meta))
        raw = dict(self._meta, nonce=_b64(nonce), ciphertext=_b64(encrypted))
        encoded = _json(raw)
        with _file_lock(self.path.with_suffix(self.path.suffix + '.lock')):
            if self._revision is None:
                if self.path.exists():
                    raise PasscodeError("密钥库已由另一个窗口建立，请重新解锁。")
            elif not self.path.exists() or hashlib.sha256(self.path.read_bytes()).digest() != self._revision:
                raise PasscodeError("密钥库已被另一个窗口修改，请锁定后重新解锁，避免覆盖新记录。")
            atomic_write(self.path, encoded)
        self._data = data
        self._revision = hashlib.sha256(encoded).digest()

    def list_keys(self):
        with self._lock:
            self._require()
            return [{k: item[k] for k in ('id', 'name', 'created')} | {
                'fingerprint': hashlib.sha256(item['key'].encode('ascii')).hexdigest()[:12],
                'default': item['id'] == self._data['default'],
            } for item in self._data['keys']]

    @property
    def default_id(self):
        self._require()
        return self._data['default']

    def get(self, identity):
        with self._lock:
            self._require()
            for item in self._data['keys']:
                if item['id'] == identity:
                    return item['key']
            raise PasscodeError("未选择有效密钥。")

    def add(self, name, key=None):
        with self._lock:
            self._require()
            name, key = _name(name), generate_key() if key is None else validate_key(key)
            if len(self._data['keys']) >= MAX_KEYS:
                raise PasscodeError("最多保存256把密钥。")
            for item in self._data['keys']:
                if item['name'] == name:
                    raise PasscodeError("密钥名称已存在，请使用其他名称。")
                if hmac.compare_digest(item['key'], key):
                    raise PasscodeError("这把密钥已经保存在密钥库中。")
            data = deepcopy(self._data)
            identity = secrets.token_hex(16)
            data['keys'].append({'id': identity, 'name': name, 'key': key,
                                 'created': datetime.now(timezone.utc).isoformat(timespec='seconds')})
            if data['default'] is None:
                data['default'] = identity
            self._commit(data)
            return identity

    def rename(self, identity, name):
        with self._lock:
            self.get(identity)
            name = _name(name)
            if any(item['name'] == name and item['id'] != identity for item in self._data['keys']):
                raise PasscodeError("密钥名称已存在。")
            data = deepcopy(self._data)
            next(item for item in data['keys'] if item['id'] == identity)['name'] = name
            self._commit(data)

    def delete(self, identity):
        with self._lock:
            self.get(identity)
            data = deepcopy(self._data)
            data['keys'] = [item for item in data['keys'] if item['id'] != identity]
            if data['default'] == identity:
                data['default'] = data['keys'][0]['id'] if data['keys'] else None
            self._commit(data)

    def set_default(self, identity):
        with self._lock:
            self.get(identity)
            data = deepcopy(self._data)
            data['default'] = identity
            self._commit(data)

    def export_backup(self, password):
        with self._lock:
            self._require()
            salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
            master = _password_key(password, salt)
            header = {'format': 'BIP-BACKUP', 'version': 1, 'salt': _b64(salt)}
            return _json(dict(header, nonce=_b64(nonce), ciphertext=_b64(AESGCM(master).encrypt(nonce, _json(self._data), _json(header)))))

    def import_backup(self, raw, password):
        with self._lock:
            self._require()
            backup = _parse(raw)
            if (backup.get('format'), backup.get('version')) != ('BIP-BACKUP', 1):
                raise PasscodeError("不是受支持的加密备份。")
            header = {'format': 'BIP-BACKUP', 'version': 1, 'salt': backup.get('salt')}
            master = _password_key(password, _unb64(backup.get('salt'), 16))
            try:
                imported = _validate_data(_parse(AESGCM(master).decrypt(_unb64(backup.get('nonce'), 12),
                                                                      _unb64(backup.get('ciphertext')), _json(header))))
            except InvalidTag:
                raise PasscodeError("备份密码不正确，或备份文件已损坏。") from None
            data = deepcopy(self._data)
            names = {item['name'] for item in data['keys']}
            existing = {item['key'] for item in data['keys']}
            added = 0
            for item in imported['keys']:
                if item['key'] in existing:
                    continue
                if len(data['keys']) >= MAX_KEYS:
                    raise PasscodeError("导入后会超过256把密钥，未执行导入。")
                copied = dict(item, id=secrets.token_hex(16))
                base, counter = copied['name'][:65], 1
                while copied['name'] in names:
                    copied['name'] = f'{base}（导入{counter}）'
                    counter += 1
                names.add(copied['name']); existing.add(copied['key'])
                data['keys'].append(copied); added += 1
            if data['default'] is None and data['keys']:
                original_default = next((item['key'] for item in imported['keys'] if item['id'] == imported.get('default')), None)
                data['default'] = next((item['id'] for item in data['keys'] if item['key'] == original_default), data['keys'][0]['id'])
            self._commit(data)
            return added
