import Foundation
import CryptoKit

@_cdecl("bip_apple_aes")
func bipAppleAES(_ encrypt: Int32, _ key: UnsafePointer<UInt8>?, _ keySize: Int32,
                 _ iv: UnsafePointer<UInt8>?, _ ivSize: Int32,
                 _ aad: UnsafePointer<UInt8>?, _ aadSize: Int32,
                 _ input: UnsafePointer<UInt8>?, _ inputSize: Int32,
                 _ output: UnsafeMutablePointer<UInt8>?, _ capacity: Int32) -> Int32 {
    guard let key, let iv, let output, keySize == 32, ivSize == 12,
          aadSize >= 0, inputSize >= 0, capacity >= 0 else { return -1 }
    func buffer(_ p: UnsafePointer<UInt8>?, _ n: Int32) -> Data {
        guard n > 0, let p else { return Data() }
        return Data(bytes: p, count: Int(n))
    }
    do {
        let secret = SymmetricKey(data: buffer(key, keySize))
        let nonce = try AES.GCM.Nonce(data: buffer(iv, ivSize))
        let data = buffer(input, inputSize), auth = buffer(aad, aadSize)
        let result: Data
        if encrypt == 1 {
            let box = try AES.GCM.seal(data, using: secret, nonce: nonce, authenticating: auth)
            result = box.ciphertext + box.tag
        } else {
            guard data.count >= 16 else { return -1 }
            let box = try AES.GCM.SealedBox(nonce: nonce, ciphertext: data.dropLast(16), tag: data.suffix(16))
            result = try AES.GCM.open(box, using: secret, authenticating: auth)
        }
        guard result.count <= Int(capacity) else { return -1 }
        result.copyBytes(to: output, count: result.count)
        return Int32(result.count)
    } catch { return -1 }
}
