"""V1.1 five-bit state codec; no application state or key-file access."""
import numpy as np
from ..errors import PasscodeError

UNIT_COUNT = 20_000
BODY_BITS = UNIT_COUNT * 5
BODY_BYTES = BODY_BITS // 8
COMMA, LOCAL, SPACE, DOT, UPPER, NUMBER = range(26, 32)
NUMBER_SYMBOLS = '+-*/=!%_:;?"<>()[]{}'
SLOTS = [v for v in range(10, 32) if v not in (DOT, NUMBER)]
SYMBOL_CODES = dict(zip(NUMBER_SYMBOLS, SLOTS))
CODE_SYMBOLS = dict(zip(SLOTS, NUMBER_SYMBOLS))

def is_extension(c):
    value = ord(c)
    basic = ('a' <= c <= 'z' or 'A' <= c <= 'Z' or '0' <= c <= '9'
             or c in ' .,\\|' or c in NUMBER_SYMBOLS)
    return value <= 0xFFFF and not 0xD800 <= value <= 0xDFFF and not basic

def logical_units(text):
    if not isinstance(text, str) or not text:
        raise PasscodeError("正文不能为空。")
    if len(text) > UNIT_COUNT:
        raise PasscodeError("正文最多20,000字符；编码后也不能超过20,000单元。")
    values = []
    numeric = upper = False
    for i, c in enumerate(text):
        if c == '.':
            values.append(DOT)
            continue
        if '0' <= c <= '9' or c in SYMBOL_CODES:
            if not numeric:
                values.append(NUMBER)
                numeric = True
            values.append(ord(c) - 48 if '0' <= c <= '9' else SYMBOL_CODES[c])
            continue
        if numeric:
            values.append(NUMBER)
            numeric = False
        if c == ' ':
            values.append(SPACE)
        elif c == ',':
            values.append(COMMA)
        elif 'a' <= c <= 'z' or 'A' <= c <= 'Z':
            needed = 'A' <= c <= 'Z'
            if needed != upper:
                values.append(UPPER)
                upper = needed
            values.append(ord(c.lower()) - 97)
        elif c == '|':
            if not upper:
                values.append(UPPER)
                upper = True
            values.append(LOCAL)
        elif c == '\\' or is_extension(c):
            if upper:
                values.append(UPPER)
                upper = False
            if c == '\\':
                values.append(LOCAL)
                if text[i+1:i+2] == 'u':
                    values.extend([UPPER, UPPER])
            else:
                cp = ord(c)
                values.extend([LOCAL, 20, (cp >> 12) & 15, (cp >> 8) & 15, (cp >> 4) & 15, cp & 15])
        else:
            raise PasscodeError(f"第{i+1}个字符不支持：请使用BMP范围内的字符，不支持代理码点及补充平面字符。")
    if numeric:
        values.append(NUMBER)
    if len(values) > UNIT_COUNT:
        raise PasscodeError(f"正文编码需要{len(values):,}单元，上限为20,000。扩展字符各占6单元，请缩短正文。")
    return values

def decode_units(values):
    output = []
    numeric = upper = False
    i = 0
    while i < len(values):
        v = int(values[i])
        if not 0 <= v < 32:
            raise PasscodeError("正文编码值无效。")
        if v == DOT:
            output.append('.')
        elif v == NUMBER:
            numeric = not numeric
        elif numeric:
            output.append(str(v) if v < 10 else CODE_SYMBOLS[v])
        elif v == UPPER:
            upper = not upper
        elif v == SPACE:
            output.append(' ')
        elif v == COMMA:
            output.append(',')
        elif v == LOCAL:
            if upper:
                output.append('|')
            elif i + 1 < len(values) and values[i+1] == 20:
                digits = values[i+2:i+6]
                if len(digits) != 4 or any(not 0 <= int(n) < 16 for n in digits):
                    raise PasscodeError("Unicode转义不完整或数值无效。")
                cp = 0
                for n in digits:
                    cp = (cp << 4) | int(n)
                if not is_extension(chr(cp)):
                    raise PasscodeError("Unicode转义字符无效。")
                output.append(chr(cp))
                i += 6
                continue
            else:
                output.append('\\')
        else:
            output.append(chr((65 if upper else 97) + v))
        i += 1
    if numeric:
        raise PasscodeError("数字编码未闭合。")
    return ''.join(output)

def pack_text(text):
    values = logical_units(text)
    padded = np.full(UNIT_COUNT, SPACE, dtype=np.uint8)
    padded[:len(values)] = values
    bits = ((padded[:, None] >> np.arange(4, -1, -1, dtype=np.uint8)) & 1).reshape(-1)
    return len(values), np.packbits(bits, bitorder='big').tobytes()

def unpack_text(body, used):
    if len(body) != BODY_BYTES or not 1 <= used <= UNIT_COUNT:
        raise PasscodeError("正文长度信息无效。")
    bits = np.unpackbits(np.frombuffer(body, dtype=np.uint8), bitorder='big').reshape(-1, 5)
    values = (bits * np.array([16, 8, 4, 2, 1], dtype=np.uint8)).sum(axis=1).astype(np.uint8)
    if np.any(values[used:] != SPACE):
        raise PasscodeError("正文填充无效。")
    return decode_units(values[:used].tolist())
