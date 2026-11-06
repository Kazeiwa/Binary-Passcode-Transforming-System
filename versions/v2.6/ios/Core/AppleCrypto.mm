#import <CommonCrypto/CommonHMAC.h>
#import <Security/Security.h>
#include "BIPCore.hpp"
// Implemented in CryptoBridge.swift. AES-GCM is supplied by public CryptoKit APIs.
extern "C" int bip_apple_aes(int,const uint8_t*,int,const uint8_t*,int,const uint8_t*,int,const uint8_t*,int,uint8_t*,int);
namespace bip {
Bytes randomBytes(size_t n){Bytes out(n);if(n&&SecRandomCopyBytes(kSecRandomDefault,n,out.data())!=errSecSuccess)throw Error("安全随机数生成失败。");return out;}
Bytes hmac(const Bytes& key,const Bytes& data){Bytes out(32);CCHmac(kCCHmacAlgSHA256,key.data(),key.size(),data.data(),data.size(),out.data());return out;}
Bytes aes(bool encrypt,const Bytes& key,const Bytes& iv,const Bytes& aad,const Bytes& data){Bytes out(data.size()+16);int n=bip_apple_aes(encrypt?1:0,key.data(),int(key.size()),iv.data(),int(iv.size()),aad.data(),int(aad.size()),data.data(),int(data.size()),out.data(),int(out.size()));if(n<0)throw Error(AUTH);out.resize(n);return out;}
}
