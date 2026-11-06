// Host-only verification backend. Never included in the iOS target.
#include "../Core/BIPCore.hpp"
#include <windows.h>
#include <bcrypt.h>
namespace bip {
static void ok(NTSTATUS n){if(n<0)throw Error("Windows host crypto failed");}
struct Algorithm {BCRYPT_ALG_HANDLE h=nullptr;Algorithm(const wchar_t* name,ULONG flags=0){ok(BCryptOpenAlgorithmProvider(&h,name,nullptr,flags));}~Algorithm(){if(h)BCryptCloseAlgorithmProvider(h,0);}};
Bytes randomBytes(size_t n){Bytes out(n);if(n)ok(BCryptGenRandom(nullptr,out.data(),ULONG(n),BCRYPT_USE_SYSTEM_PREFERRED_RNG));return out;}
Bytes hmac(const Bytes& key,const Bytes& data){Algorithm a(BCRYPT_SHA256_ALGORITHM,BCRYPT_ALG_HANDLE_HMAC_FLAG);BCRYPT_HASH_HANDLE h=nullptr;ok(BCryptCreateHash(a.h,&h,nullptr,0,const_cast<PUCHAR>(key.data()),ULONG(key.size()),0));Bytes out(32);auto status=BCryptHashData(h,const_cast<PUCHAR>(data.data()),ULONG(data.size()),0);if(status>=0)status=BCryptFinishHash(h,out.data(),32,0);BCryptDestroyHash(h);ok(status);return out;}
Bytes aes(bool encrypt,const Bytes& key,const Bytes& iv,const Bytes& aad,const Bytes& data){Algorithm a(BCRYPT_AES_ALGORITHM);ok(BCryptSetProperty(a.h,BCRYPT_CHAINING_MODE,(PUCHAR)BCRYPT_CHAIN_MODE_GCM,sizeof(BCRYPT_CHAIN_MODE_GCM),0));BCRYPT_KEY_HANDLE k=nullptr;ok(BCryptGenerateSymmetricKey(a.h,&k,nullptr,0,const_cast<PUCHAR>(key.data()),ULONG(key.size()),0));BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO info;BCRYPT_INIT_AUTH_MODE_INFO(info);Bytes tag(16);if(!encrypt){if(data.size()<16){BCryptDestroyKey(k);throw Error(AUTH);}std::copy(data.end()-16,data.end(),tag.begin());}info.pbNonce=const_cast<PUCHAR>(iv.data());info.cbNonce=ULONG(iv.size());info.pbAuthData=const_cast<PUCHAR>(aad.data());info.cbAuthData=ULONG(aad.size());info.pbTag=tag.data();info.cbTag=16;ULONG n=ULONG(data.size()-(encrypt?0:16)),done=0;Bytes out(n);auto status=encrypt?BCryptEncrypt(k,const_cast<PUCHAR>(data.data()),n,&info,nullptr,0,out.data(),n,&done,0):BCryptDecrypt(k,const_cast<PUCHAR>(data.data()),n,&info,nullptr,0,out.data(),n,&done,0);BCryptDestroyKey(k);if(status<0)throw Error(AUTH);if(encrypt)out.insert(out.end(),tag.begin(),tag.end());return out;}
}
