"""Systematic Vandermonde Reed-Solomon over GF(256): any k authenticated shards."""
from functools import lru_cache
import secrets
import numpy as np
from .errors import PasscodeError, checkpoint

EXP = np.zeros(510, dtype=np.uint8)
LOG = np.zeros(256, dtype=np.int16)
x = 1
for i in range(255):
    EXP[i] = x
    LOG[x] = i
    x <<= 1
    if x & 0x100:
        x ^= 0x11D
EXP[255:] = EXP[:255]
MUL = np.zeros((256, 256), dtype=np.uint8)
for a in range(1, 256):
    for b in range(1, 256):
        MUL[a, b] = EXP[int(LOG[a]) + int(LOG[b])]

def inverse(matrix):
    matrix = np.array(matrix, dtype=np.uint8, copy=True)
    n = len(matrix)
    output = np.eye(n, dtype=np.uint8)
    for col in range(n):
        choices = np.flatnonzero(matrix[col:, col])
        if not len(choices):
            raise PasscodeError("数据块恢复矩阵无效。")
        pivot = col + int(choices[0])
        if pivot != col:
            matrix[[col, pivot]] = matrix[[pivot, col]]
            output[[col, pivot]] = output[[pivot, col]]
        scale = EXP[255 - int(LOG[matrix[col, col]])]
        matrix[col] = MUL[scale, matrix[col]]
        output[col] = MUL[scale, output[col]]
        for row in range(n):
            factor = matrix[row, col]
            if row != col and factor:
                matrix[row] ^= MUL[factor, matrix[col]]
                output[row] ^= MUL[factor, output[col]]
    return output

def matmul(left, right, cancel=None):
    result = np.zeros((len(left), right.shape[1]), dtype=np.uint8)
    for i, row in enumerate(left):
        checkpoint(cancel)
        for coefficient, vector in zip(row, right):
            if coefficient:
                result[i] ^= MUL[coefficient, vector]
    return result

@lru_cache(maxsize=32)
def generator(n, k):
    if not 1 <= k <= n <= 255:
        raise PasscodeError("纠错块参数无效。")
    vandermonde = np.ones((n, k), dtype=np.uint8)
    for i in range(n):
        for j in range(1, k):
            vandermonde[i, j] = MUL[vandermonde[i, j-1], i+1]
    result = matmul(vandermonde, inverse(vandermonde[:k]))
    result.setflags(write=False)
    return result

def encode(data, n, k, cancel=None):
    size = (len(data) + k - 1) // k
    padded = data + secrets.token_bytes(k * size - len(data))
    source = np.frombuffer(padded, dtype=np.uint8).reshape(k, size)
    return [row.tobytes() for row in matmul(generator(n, k), source, cancel)]

def decode(shards, n, k, original_length, cancel=None):
    if len(shards) < k:
        raise PasscodeError(f"可读数据块不足：找到{len(shards)}块，至少需要{k}块；图片可能被过度裁剪或修改。")
    indices = sorted(shards)[:k]
    size = (original_length + k - 1) // k
    if any(not 0 <= i < n or len(shards[i]) != size for i in indices):
        raise PasscodeError("数据块尺寸无效。")
    source = np.stack([np.frombuffer(shards[i], dtype=np.uint8) for i in indices])
    selected = generator(n, k)[indices]
    restored = matmul(inverse(selected), source, cancel)
    return restored.tobytes()[:original_length]
