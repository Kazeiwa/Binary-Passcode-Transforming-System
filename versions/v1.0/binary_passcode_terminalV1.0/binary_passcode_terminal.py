"""二进制密码转换终端 V1.0 正式版，Python 3标准库即可运行。
格式：8位加密分钟序号 + 39位128比特随机编号 + 151位500比特掩码正文 + 2位模97校验。
时间原点：北京时间2000年1月1日00:00；不兼容旧版明文日期格式。
私钥：128位十进制字符串，前导零参与密钥计算。
两位校验用于检错，不认证密钥或抵抗主动篡改。
"""

import hashlib
import hmac
import secrets
import os
import tempfile
import base64
import unicodedata
import subprocess
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

UNIT_COUNT = 100
KEY_WIDTH = 128
DATE_WIDTH = 8
NONCE_WIDTH = 39
PAYLOAD_WIDTH = 151
PAYLOAD_BITS = UNIT_COUNT * 5
PREFIX_WIDTH = DATE_WIDTH + NONCE_WIDTH + PAYLOAD_WIDTH
CIPHER_WIDTH = PREFIX_WIDTH + 2
COMMA = 26
LOCAL = 27  # 默认模式为Unicode转义；大写模式为半角竖线。
SPACE = 28  # 数字模式中的含义由NUMBER_SYMBOLS顺序决定。
DOT = 29    # 所有模式共用的小数点/英文句号。
UPPER = 30  # 数字模式中的含义由NUMBER_SYMBOLS顺序决定。
NUMBER = 31
NUMBER_SYMBOLS = '+-*/=!%_:;?"<>()[]{}'
NUMBER_SYMBOL_SLOTS = tuple(value for value in range(10, 32) if value not in (DOT, NUMBER))
if (len(NUMBER_SYMBOLS) != len(NUMBER_SYMBOL_SLOTS)
        or len(set(NUMBER_SYMBOLS)) != len(NUMBER_SYMBOLS)
        or any(not 33 <= ord(char) <= 126 or char.isalnum() or char in ".,\\|"
               for char in NUMBER_SYMBOLS)):
    raise ValueError("数字符号表必须包含20个不重复的英文半角标点，且不能占用句点、逗号、反斜杠或竖线。")
NUMBER_SYMBOL_CODES = dict(zip(NUMBER_SYMBOLS, NUMBER_SYMBOL_SLOTS))
CODE_NUMBER_SYMBOLS = {value: char for char, value in NUMBER_SYMBOL_CODES.items()}
CHINA_TIME = timezone(timedelta(hours=8))
TIME_EPOCH = datetime(2000, 1, 1, tzinfo=CHINA_TIME)
TIME_MODULUS = 10 ** DATE_WIDTH
KEY_FILE = Path(__file__).resolve().with_name("decimal_cipher_200.key")
KEY_MAGIC = b"DECIMAL-KEY-DPAPI-V1\n"


def ascii_digits(text):
    return isinstance(text, str) and bool(text) and all("0" <= c <= "9" for c in text)


def validate_key(key):
    if not ascii_digits(key) or len(key) != KEY_WIDTH:
        raise ValueError("私钥必须是恰好128位的半角十进制数字，前导零必须保留。")
    return key


def generate_key():
    return "".join(secrets.choice("0123456789") for _ in range(KEY_WIDTH))


def validate_date(text):
    if not ascii_digits(text) or len(text) != DATE_WIDTH:
        raise ValueError("生成日期必须是YYYYMMDD格式的8位半角数字。")
    try:
        date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        raise ValueError("生成日期无效，请检查年份、月份和天数。") from None
    return text

def time_to_minutes(value=None):
    """省略时使用当前时间；无时区的datetime视为北京时间。"""
    if value is None:
        value = datetime.now(CHINA_TIME)
    elif isinstance(value, str):
        if len(value) == 8:
            validate_date(value)
            value = datetime.strptime(value, "%Y%m%d")
        elif len(value) == 12 and ascii_digits(value):
            try:
                value = datetime.strptime(value, "%Y%m%d%H%M")
            except ValueError:
                raise ValueError("生成时间无效，请检查年月日、小时和分钟。") from None
        else:
            raise ValueError("生成时间应为datetime、YYYYMMDD或YYYYMMDDHHMM。")
    if not isinstance(value, datetime):
        raise ValueError("生成时间应为datetime、YYYYMMDD或YYYYMMDDHHMM。")
    if value.tzinfo is None:
        value = value.replace(tzinfo=CHINA_TIME)
    delta = value.astimezone(CHINA_TIME) - TIME_EPOCH
    minutes = delta.days * 1440 + delta.seconds // 60
    if not 0 <= minutes < TIME_MODULUS:
        last = TIME_EPOCH + timedelta(minutes=TIME_MODULUS - 1)
        raise ValueError("生成时间超出8位分钟序号范围：北京时间2000-01-01 00:00至"
                         + last.strftime("%Y-%m-%d %H:%M") + "。")
    return minutes


def derive_time_offset(key, nonce):
    """与正文掩码分离用途；公开随机编号不等于私钥。"""
    context = b"decimal-cipher-200/v3/time\x00" + nonce.to_bytes(16, "big")
    digest = hmac.new(key.encode("ascii"), context, hashlib.sha256).digest()
    return int.from_bytes(digest, "big") % TIME_MODULUS


def is_han(char):
    value = ord(char)
    return (0x3400 <= value <= 0x4DBF or 0x4E00 <= value <= 0x9FFF
            or 0xF900 <= value <= 0xFAFF or value == 0x3007)


def is_unicode_text(char):
    """四位Unicode的汉字、假名及韩文；标点仍限英文半角列表。"""
    if is_han(char):
        return True
    value = ord(char)
    script_range = (0x3040 <= value <= 0x30FF or 0x31F0 <= value <= 0x31FF
                    or 0xFF66 <= value <= 0xFF9F or 0x1100 <= value <= 0x11FF
                    or 0x3130 <= value <= 0x318F or 0xA960 <= value <= 0xA97F
                    or 0xAC00 <= value <= 0xD7A3 or 0xD7B0 <= value <= 0xD7FF)
    return script_range and (unicodedata.category(char)[0] in "LM" or char in "゛゜")


def logical_units(text):
    """V2状态编码：默认、小写/大写、数字；Unicode转义占6单元。"""
    if not isinstance(text, str) or not text:
        raise ValueError("正文不能为空。")
    if len(text) > UNIT_COUNT:
        raise ValueError(f"正文最多100个字符，当前有{len(text)}个字符，请缩短后重试。")
    units = []
    numeric = False
    upper = False
    for position, char in enumerate(text, 1):
        if char == ".":
            units.append(DOT)
            continue
        if "0" <= char <= "9" or char in NUMBER_SYMBOLS:
            if not numeric:
                units.append(NUMBER)
                numeric = True
            units.append(int(char) if char.isdigit() else NUMBER_SYMBOL_CODES[char])
            continue
        if numeric:
            units.append(NUMBER)
            numeric = False
        if char == " ":
            units.append(SPACE)
        elif char == ",":
            units.append(COMMA)
        elif "a" <= char <= "z" or "A" <= char <= "Z":
            needs_upper = "A" <= char <= "Z"
            if needs_upper != upper:
                units.append(UPPER)
                upper = needs_upper
            units.append(ord(char.lower()) - ord("a"))
        elif char == "|":
            if not upper:
                units.append(UPPER)
                upper = True
            units.append(LOCAL)
        elif char == "\\" or is_unicode_text(char):
            if upper:
                units.append(UPPER)
                upper = False
            if char == "\\":
                units.append(LOCAL)
                # 字面反斜杠占一个单元。若原文紧接字面上的小写u，
                # 插入连续两次大写切换（无字符输出），隔开Unicode前缀。
                if text[position:position + 1] == "u":
                    units.extend((UPPER, UPPER))
            else:
                # 默认模式下：反斜杠、u、四个原始十六进制码值。
                units.extend((LOCAL, ord("u") - ord("a")))
                units.extend(int(digit, 16) for digit in f"{ord(char):04x}")
        else:
            raise ValueError(
                f"第{position}个字符{char!r}不支持：请使用英文字母、半角数字和标点，"
                "或常用汉字、日文假名、韩文；不支持全角标点、表情及部分生僻字。"
            )
    if numeric:
        units.append(NUMBER)
    if len(units) > UNIT_COUNT:
        raise ValueError(
            f"正文超出容量：需要{len(units)}个容量单元，上限为100个。"
            "每个汉字、假名或韩文字符占6个单元，混合输入还会占用额外容量，请缩短正文。"
        )
    return units


def prepare_units(text):
    """关闭数字模式后用空格补足100个单元，不要求重置大小写状态。"""
    base = logical_units(text)
    padded = base + [SPACE] * (UNIT_COUNT - len(base))
    return padded


def decode_values(values):
    result = []
    numeric = False
    upper = False
    index = 0
    while index < len(values):
        value = values[index]
        if type(value) is not int or not 0 <= value <= 31:
            raise ValueError("密文中的字符编码无效，请检查密文及所用密钥。")
        if value == DOT:
            result.append(".")
        elif value == NUMBER:
            numeric = not numeric
        elif numeric:
            result.append(str(value) if value < 10 else CODE_NUMBER_SYMBOLS[value])
        elif value == UPPER:
            upper = not upper
        elif value == SPACE:
            result.append(" ")
        elif value == COMMA:
            result.append(",")
        elif value == LOCAL:
            if upper:
                result.append("|")
            elif values[index + 1:index + 2] == [ord("u") - ord("a")]:
                if index + 5 >= len(values):
                    raise ValueError("密文中的文字编码不完整，请检查密文及所用密钥。")
                if not all(type(v) is int and 0 <= v < 16 for v in values[index + 2:index + 6]):
                    raise ValueError("密文中的文字编码无效，请检查密文及所用密钥。")
                code = 0
                for digit in values[index + 2:index + 6]:
                    code = (code << 4) | digit
                char = chr(code)
                if not is_unicode_text(char):
                    raise ValueError("密文包含不支持的文字，请检查密文及所用密钥。")
                result.append(char)
                index += 6
                continue
            else:
                result.append("\\")
        elif 0 <= value <= 25:
            result.append(chr((ord("A") if upper else ord("a")) + value))
        else:
            raise ValueError(
                "密文无法解读，可能是密钥不匹配或密文已损坏。"
            )
        index += 1
    if numeric:
        raise ValueError("密文中的数字内容不完整，请检查密文及所用密钥。")
    return "".join(result)


def checksum(prefix):
    """使完整200位数除以97余1；校验码采用唯一的02—98表示。"""
    if not ascii_digits(prefix) or len(prefix) != PREFIX_WIDTH:
        raise ValueError("计算校验码需要恰好198位半角十进制数字。")
    return f"{98 - (int(prefix) * 100) % 97:02d}"


def inspect_cipher(cipher):
    """公开校验；首8位已经加密，不能按日历日期判断是否合法。"""
    if not isinstance(cipher, str):
        raise ValueError("密文必须以字符串输入，不能丢失前导零。")
    if len(cipher) != CIPHER_WIDTH:
        reason = "不足" if len(cipher) < CIPHER_WIDTH else "过长"
        raise ValueError(f"密文长度{reason}：必须是200位，实际为{len(cipher)}位；不能自动补齐或截断。")
    if not ascii_digits(cipher):
        raise ValueError("密文只能包含半角数字0—9，不允许空格、换行或其他符号。")
    prefix = cipher[:-2]
    if not hmac.compare_digest(checksum(prefix), cipher[-2:]):
        raise ValueError("校验码不正确，密文可能输入错误或已经损坏。")
    encrypted_time = int(cipher[:DATE_WIDTH])
    nonce_end = DATE_WIDTH + NONCE_WIDTH
    nonce = int(cipher[DATE_WIDTH:nonce_end])
    payload = int(cipher[nonce_end:-2])
    if nonce >= 1 << 128:
        raise ValueError("密文的随机编号无效，请检查是否复制完整且未被修改。")
    if payload >= 1 << PAYLOAD_BITS:
        raise ValueError("密文的正文数据无效，请检查是否复制完整且未被修改。")
    return encrypted_time, nonce, payload


def derive_mask(key, minutes, nonce):
    """先还原分钟序号，再以该序号、随机编号及分块序号派生正文掩码。"""
    context = (b"decimal-cipher-200/v3/mask\x00"
               + f"{minutes:08d}".encode("ascii") + nonce.to_bytes(16, "big"))
    material = b"".join(
        hmac.new(key.encode("ascii"), context + i.to_bytes(2, "big"), hashlib.sha256).digest()
        for i in range(2)
    )
    return int.from_bytes(material, "big") >> (512 - PAYLOAD_BITS)


def encrypt(text, key, generation_date=None):
    """保留旧参数名；现也接受精确到分的datetime或12位时间。"""
    validate_key(key)
    minutes = time_to_minutes(generation_date)
    values = prepare_units(text)
    plain = int("".join(f"{value:05b}" for value in values), 2)
    nonce = secrets.randbits(128)
    encrypted_time = (minutes + derive_time_offset(key, nonce)) % TIME_MODULUS
    payload = plain ^ derive_mask(key, minutes, nonce)
    prefix = f"{encrypted_time:08d}{nonce:039d}{payload:0151d}"
    return prefix + checksum(prefix)


def decrypt(cipher, key):
    return decrypt_with_time(cipher, key)[1]


def decrypt_with_time(cipher, key):
    """按顺序先还原时间，再解密正文，返回北京时间和正文。"""
    encrypted_time, nonce, payload = inspect_cipher(cipher)
    validate_key(key)
    minutes = (encrypted_time - derive_time_offset(key, nonce)) % TIME_MODULUS
    generated_at = TIME_EPOCH + timedelta(minutes=minutes)
    plain = payload ^ derive_mask(key, minutes, nonce)
    bits = f"{plain:0500b}"
    values = [int(bits[i:i + 5], 2) for i in range(0, PAYLOAD_BITS, 5)]
    return generated_at, decode_values(values)


def protect_local_bytes(data, decrypt=False):
    """Windows当前用户范围DPAPI；不采用整台机器共享的保护范围。"""
    if os.name != "nt":
        raise ValueError("本地加密存储需要Windows；不会退回明文保存。")
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.POINTER(Blob)
    crypt32.CryptProtectData.argtypes = [pointer, wintypes.LPCWSTR, pointer,
                                        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, pointer]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [pointer, ctypes.POINTER(wintypes.LPWSTR), pointer,
                                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, pointer]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    if decrypt:
        ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1,
                                        ctypes.byref(output))
    else:
        ok = crypt32.CryptProtectData(ctypes.byref(source), "Decimal Cipher 200 key", None,
                                      None, None, 1, ctypes.byref(output))
    if not ok:
        if decrypt:
            raise ValueError("本机密钥解密失败：可能属于其他电脑或用户，或文件已损坏，请重新导入原始密钥。")
        raise ValueError(f"Windows本地密钥保护失败，系统错误码{ctypes.get_last_error()}；未保存明文。")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def linux_keyring(operation, key=None):
    """通过Secret Service存储；与C++版共用条目，不写明文文件。"""
    attributes = ["application", "decimal_cipher_200", "account", "default"]
    if operation == "store":
        validate_key(key)
        arguments = ["secret-tool", "store", "--label=Decimal Cipher 200", *attributes]
    else:
        arguments = ["secret-tool", "lookup", *attributes]
    try:
        result = subprocess.run(arguments, input=key + "\n" if operation == "store" else "",
                                capture_output=True, text=True, encoding="utf-8", check=False)
    except FileNotFoundError:
        raise ValueError("未找到系统密钥环工具，请安装libsecret-tools后重试。") from None
    except (OSError, UnicodeError):
        raise ValueError("无法访问系统密钥环，请检查桌面登录状态并重试。") from None
    if operation == "lookup" and result.returncode == 1 and not result.stdout and not result.stderr:
        return None
    if result.returncode != 0:
        raise ValueError("系统密钥环访问失败，请确认已登录桌面、密钥环服务已启动且已解锁。")
    if operation == "lookup":
        return validate_key(result.stdout.rstrip("\r\n"))
    return None


def load_saved_key():
    if sys.platform.startswith("linux"):
        return linux_keyring("lookup")
    if os.name != "nt":
        raise ValueError("当前系统暂不支持本地密钥存储，请使用Windows或Linux。")
    try:
        data = KEY_FILE.read_bytes()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as error:
        raise ValueError("无法读取固定密钥文件，请进入密钥管理重新保存。") from error
    # 自动迁移旧版的128位明文文件，文件路径保持不变。
    if len(data) == KEY_WIDTH and all(48 <= char <= 57 for char in data):
        key = data.decode("ascii")
        save_fixed_key(key, replace=True)
        return key
    if not data.startswith(KEY_MAGIC):
        raise ValueError("固定密钥文件格式不正确，请进入密钥管理更新密钥。") from None
    try:
        protected = base64.b64decode(data[len(KEY_MAGIC):], validate=True)
    except ValueError:
        raise ValueError("本地密钥文件编码损坏，请重新导入原始密钥。") from None
    if not protected:
        raise ValueError("本地密钥文件内容为空，请重新导入原始密钥。")
    try:
        key = protect_local_bytes(protected, decrypt=True).decode("ascii")
        return validate_key(key)
    except UnicodeError:
        raise ValueError("本地密钥内容无效，请重新导入原始密钥。") from None


def save_fixed_key(key, replace=False):
    validate_key(key)
    if sys.platform.startswith("linux"):
        if not replace and linux_keyring("lookup") is not None:
            raise ValueError("已经保存密钥，如需更换请使用更新密钥选项。")
        linux_keyring("store", key)
        return
    if os.name != "nt":
        raise ValueError("当前系统暂不支持本地密钥存储，请使用Windows或Linux。")
    if KEY_FILE.exists() and not replace:
        raise ValueError("已经保存固定密钥，如需更换请使用更新密钥选项。")
    protected = KEY_MAGIC + base64.b64encode(protect_local_bytes(key.encode("ascii")))
    temporary = None
    try:
        # 在同一目录写完后再替换，避免保存中断产生半截密钥。
        with tempfile.NamedTemporaryFile(mode="wb", dir=KEY_FILE.parent,
                                         prefix=".decimal-key-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(protected)
        os.replace(temporary, KEY_FILE)
    except OSError as error:
        raise ValueError("密钥保存失败，请检查程序所在文件夹是否允许写入。") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def require_saved_key():
    key = load_saved_key()
    if key is None:
        raise ValueError("尚未保存固定密钥，请先进入“3密钥管理”导入或生成密钥。")
    return key


def key_management():
    print("\n密钥管理")
    print("本地密钥使用系统密钥环保存。" if sys.platform.startswith("linux") else "本地密钥使用本机账户加密保护。")
    print("更换密钥前可选择4显示并自行备份旧密钥，以便读取旧消息。")
    while True:
        try:
            print("\n1 查看密钥状态\n2 导入或更新密钥\n3 随机生成并保存新密钥\n4 显示当前密钥\n0 返回主菜单")
            action = input("请选择：")
            if action == "0":
                return
            if action == "1":
                print("已配置有效密钥。" if load_saved_key() is not None
                      else "尚未配置密钥，请选择2导入或3生成。")
            elif action == "2":
                key = input("请输入要导入或更新的128位密钥：")
                save_fixed_key(key, replace=True)
                print("固定密钥已更新。")
            elif action == "3":
                key = generate_key()
                save_fixed_key(key, replace=True)
                print("新密钥已生成并安全保存。需要传递或备份时请选择4显示。")
            elif action == "4":
                print("当前密钥（复制后可在接收方的密钥管理中导入）：")
                print(require_saved_key())
            else:
                print("错误：请选择0—4。")
        except ValueError as error:
            print("错误：" + str(error))


def main():
    print("二进制密码转换终端 V1.0")
    while True:
        try:
            print("\n1 加密正文\n2 解密密文\n3 密钥管理\n0 退出程序")
            action = input("请选择：")
            if action == "0":
                break
            if action == "3":
                key_management()
            elif action == "1":
                key = require_saved_key()
                print("支持大小写英文字母、半角数字、空格、英文句号和逗号、反斜杠、竖线。")
                print("支持常用简繁汉字、日文平假名/片假名和韩文；标点请使用英文半角。")
                print("其他支持的英文半角符号：" + NUMBER_SYMBOLS)
                print("最多输入100字符；中文、日文、韩文及混合输入会占用更多容量。")
                text = input("请输入正文：")
                print("加密结果：")
                print(encrypt(text, key))
            elif action == "2":
                key = require_saved_key()
                cipher = input("请输入恰好200位的十进制密文：")
                generated_at, result = decrypt_with_time(cipher, key)
                print("生成时间（北京时间）：" + generated_at.strftime("%Y-%m-%d %H:%M"))
                print("解密结果：" + result)
            else:
                print("错误：只能输入0、1、2或3。")
        except ValueError as error:
            print("错误：" + str(error))
        except (EOFError, KeyboardInterrupt):
            print("\n程序已退出。")
            break
        print()


if __name__ == "__main__":
    main()

