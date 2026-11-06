// 二进制密码转换终端 V1.1. C++17; Windows/Linux CLI and Android JNI core.
#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#if defined(__ANDROID__)
#include <jni.h>
#elif defined(_WIN32)
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <wincrypt.h>
#else
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/random.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

using Bytes = std::vector<unsigned char>;
using Units = std::vector<int>;
namespace fs = std::filesystem;
constexpr int COMMA=26, LOCAL=27, SPACE=28, DOT=29, UPPER=30, NUMBER=31;
const std::string SYMBOLS="+-*/=!%_:;?\"<>()[]{}";
const std::string KEY_MAGIC="DECIMAL-KEY-DPAPI-V1\n";

#ifdef __ANDROID__
thread_local JNIEnv* android_env=nullptr;
thread_local jclass android_bridge=nullptr;
#endif

[[noreturn]] void fail(const std::string& text) { throw std::runtime_error(text); }
#ifdef __ANDROID__
void android_check() {
    if(!android_env||!android_bridge)fail("Android加密服务尚未初始化。");
    if(android_env->ExceptionCheck()){android_env->ExceptionClear();fail("Android系统加密服务调用失败。");}
}
jbyteArray android_array(const Bytes& bytes) {
    auto array=android_env->NewByteArray(jsize(bytes.size()));android_check();
    if(!array)fail("无法分配加密数据。");
    if(!bytes.empty())android_env->SetByteArrayRegion(array,0,jsize(bytes.size()),reinterpret_cast<const jbyte*>(bytes.data()));
    android_check();return array;
}
Bytes android_result(jbyteArray array) {
    android_check();if(!array)fail("Android加密服务未返回结果。");
    Bytes bytes(size_t(android_env->GetArrayLength(array)));
    if(!bytes.empty())android_env->GetByteArrayRegion(array,0,jsize(bytes.size()),reinterpret_cast<jbyte*>(bytes.data()));
    android_env->DeleteLocalRef(array);android_check();return bytes;
}
#endif
bool digits(const std::string& s) {
    return !s.empty() && std::all_of(s.begin(),s.end(),[](char c){return c>='0'&&c<='9';});
}
void check_key(const std::string& s) {
    if(s.size()!=128 || !digits(s)) fail("私钥必须是恰好128位半角数字，前导零必须保留。");
}
std::string pad(std::string s, size_t n) {
    if(s.size()>n) fail("数值超出字段长度。");
    return std::string(n-s.size(),'0')+s;
}

std::u32string utf8_decode(const std::string& s) {
    std::u32string out;
    for(size_t i=0;i<s.size();) {
        unsigned char first=s[i++]; uint32_t c; int extra;
        if(first<128) { c=first; extra=0; }
        else if(first>=0xc2 && first<=0xdf) {c=first&31;extra=1;}
        else if(first>=0xe0 && first<=0xef) {c=first&15;extra=2;}
        else if(first>=0xf0 && first<=0xf4) {c=first&7;extra=3;}
        else fail("输入不是合法UTF-8文本。");
        if(i+extra>s.size()) fail("UTF-8字符不完整。");
        for(int j=0;j<extra;++j) {unsigned char b=s[i++];if((b&0xc0)!=0x80)fail("UTF-8字符不合法。");c=(c<<6)|(b&63);}
        if((extra==1&&c<0x80)||(extra==2&&c<0x800)||(extra==3&&c<0x10000)
            || c>0x10ffff || (c>=0xd800&&c<=0xdfff)) fail("UTF-8字符不合法。");
        out.push_back(c);
    }
    return out;
}
std::string utf8_encode(const std::u32string& text) {
    std::string out;
    for(uint32_t c:text) {
        if(c<128)out.push_back(char(c));
        else if(c<0x800){out.push_back(char(0xc0|(c>>6)));out.push_back(char(0x80|(c&63)));}
        else if(c<0x10000){out.push_back(char(0xe0|(c>>12)));out.push_back(char(0x80|((c>>6)&63)));out.push_back(char(0x80|(c&63)));}
        else {out.push_back(char(0xf0|(c>>18)));out.push_back(char(0x80|((c>>12)&63)));out.push_back(char(0x80|((c>>6)&63)));out.push_back(char(0x80|(c&63)));}
    }
    return out;
}

// Six-unit escapes cover BMP scalar values, excluding the base alphabet.
bool unicode_text(uint32_t c) {
    if(c>0xffff||(c>=0xd800&&c<=0xdfff))return false;
    if(c<128&&((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')
        ||std::string(" .,\\|").find(char(c))!=std::string::npos||SYMBOLS.find(char(c))!=std::string::npos))return false;
    return true;
}
int symbol_code(char32_t c) {
    if(c>127)return -1;
    auto p=SYMBOLS.find(char(c));
    if(p==std::string::npos)return -1;
    return p<19 ? int(p)+10 : 30;
}
char symbol_for(int value) {
    int index=value==30?19:value-10;
    if(index<0||index>=20)fail("数字模式码值不合法。");
    return SYMBOLS[index];
}
Units logical_units(const std::string& input) {
    auto text=utf8_decode(input);
    if(text.empty())fail("正文不能为空。");
    if(text.size()>100)fail("正文最多100个字符，当前有"+std::to_string(text.size())+"个字符。");
    Units out;bool numeric=false,upper=false;
    for(size_t i=0;i<text.size();++i) {
        uint32_t c=text[i];
        if(c=='.'){out.push_back(DOT);continue;}
        int symbol=symbol_code(c);
        if((c>='0'&&c<='9')||symbol>=0) {
            if(!numeric){out.push_back(NUMBER);numeric=true;}
            out.push_back(c>='0'&&c<='9'?int(c-'0'):symbol);continue;
        }
        if(numeric){out.push_back(NUMBER);numeric=false;}
        if(c==' ')out.push_back(SPACE);
        else if(c==',')out.push_back(COMMA);
        else if((c>='a'&&c<='z')||(c>='A'&&c<='Z')) {
            bool needed=c>='A'&&c<='Z';
            if(needed!=upper){out.push_back(UPPER);upper=needed;}
            out.push_back(int(c-(needed?'A':'a')));
        } else if(c=='|') {
            if(!upper){out.push_back(UPPER);upper=true;}out.push_back(LOCAL);
        } else if(c=='\\'||unicode_text(c)) {
            if(upper){out.push_back(UPPER);upper=false;}
            out.push_back(LOCAL);
            if(c=='\\') {
                if(i+1<text.size()&&text[i+1]=='u'){out.push_back(UPPER);out.push_back(UPPER);}
            } else {
                out.push_back(20);
                for(int shift=12;shift>=0;shift-=4)out.push_back(int((c>>shift)&15));
            }
        } else fail("第"+std::to_string(i+1)+"个字符不支持：仅支持Unicode基本多文种平面（BMP）内的字符，不支持代理码点及补充平面字符。");
    }
    if(numeric)out.push_back(NUMBER);
    if(out.size()>100)fail("正文超出容量：需要"+std::to_string(out.size())+"个容量单元，上限为100个。基础字符以外的BMP字符各占6个单元，混合输入还会占用额外容量，请缩短正文。");
    return out;
}
std::string decode_units(const Units& values) {
    std::u32string out;bool numeric=false,upper=false;
    for(size_t i=0;i<values.size();) {
        int v=values[i];if(v<0||v>31)fail("密文中的字符编码无效，请检查密文及所用密钥。");
        if(v==DOT)out.push_back('.');
        else if(v==NUMBER)numeric=!numeric;
        else if(numeric)out.push_back(v<10?char32_t('0'+v):char32_t(symbol_for(v)));
        else if(v==UPPER)upper=!upper;
        else if(v==SPACE)out.push_back(' ');
        else if(v==COMMA)out.push_back(',');
        else if(v==LOCAL) {
            if(upper)out.push_back('|');
            else if(i+1<values.size()&&values[i+1]==20) {
                if(i+5>=values.size())fail("密文中的文字编码不完整，请检查密文及所用密钥。");
                uint32_t c=0;
                for(size_t j=i+2;j<i+6;++j){if(values[j]<0||values[j]>15)fail("密文中的文字编码无效，请检查密文及所用密钥。");c=(c<<4)|values[j];}
                if(!unicode_text(c))fail("密文包含不支持的文字，请检查密文及所用密钥。");
                out.push_back(c);i+=6;continue;
            } else out.push_back('\\');
        } else if(v<=25)out.push_back((upper?'A':'a')+v);
        else fail("密文无法解读，可能是密钥不匹配或密文已损坏。");
        ++i;
    }
    if(numeric)fail("密文中的数字内容不完整，请检查密文及所用密钥。");
    return utf8_encode(out);
}

Bytes random_bytes(size_t size) {
    Bytes out(size);
#if defined(__ANDROID__)
    android_check();auto method=android_env->GetStaticMethodID(android_bridge,"randomBytes","(I)[B");android_check();
    out=android_result(static_cast<jbyteArray>(android_env->CallStaticObjectMethod(android_bridge,method,jint(size))));
    if(out.size()!=size)fail("系统随机数长度无效。");
#elif defined(_WIN32)
    if(BCryptGenRandom(nullptr,out.data(),ULONG(size),BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0)fail("系统随机数生成失败。");
#else
    size_t done=0;
    while(done<size){ssize_t n=getrandom(out.data()+done,size-done,0);if(n<0&&errno==EINTR)continue;if(n<=0)fail("系统随机数生成失败。");done+=size_t(n);}
#endif
    return out;
}
std::string generate_key() {
    std::string key;
    while(key.size()<128){for(auto b:random_bytes(64))if(b<250){key.push_back(char('0'+b%10));if(key.size()==128)break;}}
    return key;
}
Bytes hmac_sha256(const std::string& key,const Bytes& data) {
    Bytes out(32);
#if defined(__ANDROID__)
    android_check();auto method=android_env->GetStaticMethodID(android_bridge,"hmacSha256","([B[B)[B");android_check();
    auto key_array=android_array(Bytes(key.begin(),key.end())),data_array=android_array(data);
    auto result=static_cast<jbyteArray>(android_env->CallStaticObjectMethod(android_bridge,method,key_array,data_array));
    android_env->DeleteLocalRef(key_array);android_env->DeleteLocalRef(data_array);
    out=android_result(result);if(out.size()!=32)fail("系统HMAC结果长度无效。");
#elif defined(_WIN32)
    BCRYPT_ALG_HANDLE alg=nullptr;BCRYPT_HASH_HANDLE hash=nullptr;Bytes object;
    try {
        if(BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,nullptr,BCRYPT_ALG_HANDLE_HMAC_FLAG)<0)fail("无法初始化HMAC。");
        ULONG size=0,used=0;
        if(BCryptGetProperty(alg,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&size),sizeof(size),&used,0)<0)fail("读取HMAC参数失败。");
        object.resize(size);
        if(BCryptCreateHash(alg,&hash,object.data(),size,reinterpret_cast<PUCHAR>(const_cast<char*>(key.data())),ULONG(key.size()),0)<0)fail("创建HMAC失败。");
        if(BCryptHashData(hash,const_cast<PUCHAR>(data.data()),ULONG(data.size()),0)<0
            ||BCryptFinishHash(hash,out.data(),ULONG(out.size()),0)<0)fail("HMAC计算失败。");
        BCryptDestroyHash(hash);hash=nullptr;BCryptCloseAlgorithmProvider(alg,0);alg=nullptr;
    } catch(...) {if(hash)BCryptDestroyHash(hash);if(alg)BCryptCloseAlgorithmProvider(alg,0);throw;}
#else
    static void* library=[](){void* p=dlopen("libcrypto.so.3",RTLD_NOW|RTLD_LOCAL);if(!p)p=dlopen("libcrypto.so.1.1",RTLD_NOW|RTLD_LOCAL);if(!p)fail("需要安装OpenSSL运行库libcrypto（版本3或1.1）。");return p;}();
    using Md=const void*(*)();
    using Hmac=unsigned char*(*)(const void*,const void*,int,const unsigned char*,size_t,unsigned char*,unsigned int*);
    auto md=reinterpret_cast<Md>(dlsym(library,"EVP_sha256"));
    auto mac=reinterpret_cast<Hmac>(dlsym(library,"HMAC"));
    if(!md||!mac)fail("OpenSSL运行库缺少HMAC接口。");
    unsigned int size=0;
    if(!mac(md(),key.data(),int(key.size()),data.data(),data.size(),out.data(),&size)||size!=32)fail("HMAC计算失败。");
#endif
    return out;
}
std::string bits_of(const Bytes& bytes) {
    std::string bits;for(auto b:bytes)for(int i=7;i>=0;--i)bits.push_back(char('0'+((b>>i)&1)));return bits;
}
std::string binary_to_decimal(const std::string& bits,size_t width) {
    std::string d="0";
    for(char bit:bits){int carry=bit-'0';for(size_t j=d.size();j-->0;){int n=(d[j]-'0')*2+carry;d[j]=char('0'+n%10);carry=n/10;}if(carry)d.insert(d.begin(),char('0'+carry));}
    return pad(d,width);
}
std::string decimal_to_binary(std::string decimal,size_t width) {
    if(!digits(decimal))fail("数值不是合法半角数字。");
    size_t start=decimal.find_first_not_of('0');decimal=start==std::string::npos?"0":decimal.substr(start);
    std::string bits;
    while(decimal!="0") {
        std::string quotient;int remainder=0;
        for(char c:decimal){int n=remainder*10+c-'0';int q=n/2;remainder=n%2;if(q||!quotient.empty())quotient.push_back(char('0'+q));}
        bits.push_back(char('0'+remainder));decimal=quotient.empty()?"0":quotient;
        if(bits.size()>width)fail("密文字段超出二进制数值范围。");
    }
    std::reverse(bits.begin(),bits.end());return std::string(width-bits.size(),'0')+bits;
}
Bytes bytes_of(const std::string& bits) {
    Bytes out;for(size_t i=0;i<bits.size();i+=8){int b=0;for(int j=0;j<8;++j)b=(b<<1)|(bits[i+j]-'0');out.push_back(static_cast<unsigned char>(b));}return out;
}
constexpr int64_t TIME_MODULUS=100000000, TIME_EPOCH_SECONDS=946656000;
int64_t time_offset(const std::string& key,const Bytes& nonce) {
    const char label[]="decimal-cipher-200/v3/time";
    Bytes context(label,label+sizeof(label));context.insert(context.end(),nonce.begin(),nonce.end());
    int64_t remainder=0;for(auto b:hmac_sha256(key,context))remainder=(remainder*256+b)%TIME_MODULUS;
    return remainder;
}
std::string mask_bits(const std::string& key,int64_t minutes,const Bytes& nonce) {
    const char label[]="decimal-cipher-200/v3/mask";
    Bytes context(label,label+sizeof(label)); // sizeof includes the required NUL separator.
    auto day=pad(std::to_string(minutes),8);
    context.insert(context.end(),day.begin(),day.end());context.insert(context.end(),nonce.begin(),nonce.end());
    Bytes material;
    for(int i=0;i<2;++i){auto data=context;data.push_back(0);data.push_back(static_cast<unsigned char>(i));auto block=hmac_sha256(key,data);material.insert(material.end(),block.begin(),block.end());}
    return bits_of(material).substr(0,500);
}
std::string checksum(const std::string& prefix) {
    if(prefix.size()!=198||!digits(prefix))fail("计算校验码需要198位半角数字。");
    int remainder=0;for(char c:prefix)remainder=(remainder*10+c-'0')%97;
    return pad(std::to_string(98-remainder*100%97),2);
}
void check_date(const std::string& s) {
    if(s.size()!=8||!digits(s))fail("日期必须是YYYYMMDD格式。");
    int y=std::stoi(s.substr(0,4)),m=std::stoi(s.substr(4,2)),d=std::stoi(s.substr(6,2));
    const int days[]={0,31,28,31,30,31,30,31,31,30,31,30,31};
    if(y<1||m<1||m>12)fail("生成日期无效。");
    int maximum=days[m]+(m==2&&y%4==0&&(y%100!=0||y%400==0));
    if(d<1||d>maximum)fail("生成日期无效。");
}
int64_t time_to_minutes(const std::string& s) {
    int64_t minutes;
    if(s.empty()) {
        auto seconds=std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
        if(seconds<TIME_EPOCH_SECONDS)fail("生成时间超出可用范围：北京时间2000-01-01 00:00至2190-02-17 10:39。");
        minutes=(seconds-TIME_EPOCH_SECONDS)/60;
    } else {
        if((s.size()!=8&&s.size()!=12)||!digits(s))fail("生成时间格式无效。");
        check_date(s.substr(0,8));
        int y=std::stoi(s.substr(0,4)),m=std::stoi(s.substr(4,2)),d=std::stoi(s.substr(6,2));
        int hour=s.size()==12?std::stoi(s.substr(8,2)):0,minute=s.size()==12?std::stoi(s.substr(10,2)):0;
        if(hour>23||minute>59)fail("生成时间无效，请检查小时和分钟。");
        auto before_year=[](int year)->int64_t{int64_t n=year-1;return 365*n+n/4-n/100+n/400;};
        const int month_days[]={0,31,28,31,30,31,30,31,31,30,31,30,31};
        int64_t days=before_year(y)-before_year(2000)+d-1;
        for(int i=1;i<m;++i)days+=month_days[i]+(i==2&&y%4==0&&(y%100!=0||y%400==0));
        minutes=days*1440+hour*60+minute;
    }
    if(minutes<0||minutes>=TIME_MODULUS)fail("生成时间超出可用范围：北京时间2000-01-01 00:00至2190-02-17 10:39。");
    return minutes;
}
std::string format_time(int64_t minutes) {
    // Gregorian arithmetic also works beyond 2038 on 32-bit Android time_t.
    if(minutes<0||minutes>=TIME_MODULUS)fail("生成时间无法显示。");
    auto leap=[](int y){return y%4==0&&(y%100!=0||y%400==0);};
    int64_t days=minutes/1440;int y=2000,m=1;
    while(days>=365+leap(y)){days-=365+leap(y);++y;}
    const int month_days[]={0,31,28,31,30,31,30,31,31,30,31,30,31};
    while(days>=month_days[m]+(m==2&&leap(y))){days-=month_days[m]+(m==2&&leap(y));++m;}
    char text[32];std::snprintf(text,sizeof(text),"%04d-%02d-%02d %02d:%02d",y,m,int(days)+1,int(minutes%1440/60),int(minutes%60));
    return text;
}
struct Frame {int64_t encrypted_time;std::string nonce_bits,payload_bits;};
Frame inspect_cipher(const std::string& cipher) {
    if(cipher.size()!=200)fail("密文必须恰好200位，当前为"+std::to_string(cipher.size())+"位；不能补齐或截断。");
    if(!digits(cipher))fail("密文只能含半角数字，不能有空格、换行或其他符号。");
    if(checksum(cipher.substr(0,198))!=cipher.substr(198))fail("校验码不正确，密文可能输入错误或损坏。");
    return {std::stoll(cipher.substr(0,8)),decimal_to_binary(cipher.substr(8,39),128),decimal_to_binary(cipher.substr(47,151),500)};
}
std::string encrypt(const std::string& text,const std::string& key,std::string day="",std::string nonce_decimal="") {
    check_key(key);auto minutes=time_to_minutes(day);
    Units units=logical_units(text);units.resize(100,SPACE);
    Bytes nonce=nonce_decimal.empty()?random_bytes(16):bytes_of(decimal_to_binary(nonce_decimal,128));
    auto encrypted_time=(minutes+time_offset(key,nonce))%TIME_MODULUS;
    std::string mask=mask_bits(key,minutes,nonce),plain;
    for(int v:units)for(int i=4;i>=0;--i)plain.push_back(char('0'+((v>>i)&1)));
    for(size_t i=0;i<500;++i)plain[i]=char('0'+((plain[i]-'0')^(mask[i]-'0')));
    std::string prefix=pad(std::to_string(encrypted_time),8)+binary_to_decimal(bits_of(nonce),39)+binary_to_decimal(plain,151);
    return prefix+checksum(prefix);
}
std::pair<std::string,std::string> decrypt_with_time(const std::string& cipher,const std::string& key) {
    auto frame=inspect_cipher(cipher);check_key(key);
    auto nonce=bytes_of(frame.nonce_bits);
    auto minutes=(frame.encrypted_time-time_offset(key,nonce)+TIME_MODULUS)%TIME_MODULUS;
    std::string mask=mask_bits(key,minutes,nonce);Units units;
    for(int i=0;i<500;i+=5){int v=0;for(int j=0;j<5;++j)v=(v<<1)|((frame.payload_bits[i+j]-'0')^(mask[i+j]-'0'));units.push_back(v);}
    return {format_time(minutes),decode_units(units)};
}
std::string decrypt(const std::string& cipher,const std::string& key) {return decrypt_with_time(cipher,key).second;}

#ifndef __ANDROID__
#ifdef _WIN32
Bytes dpapi(const Bytes& source,bool decrypting=false) {
    DATA_BLOB in{DWORD(source.size()),const_cast<BYTE*>(source.data())},out{};
    BOOL ok=decrypting?CryptUnprotectData(&in,nullptr,nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&out)
        :CryptProtectData(&in,L"Decimal Cipher 200 key",nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&out);
    if(!ok)fail(decrypting?"本机密钥解密失败，可能属于其他用户/电脑或文件已损坏。请重新导入原始密钥。":"Windows密钥加密保存失败，未保存明文。");
    Bytes result(out.pbData,out.pbData+out.cbData);LocalFree(out.pbData);return result;
}
std::string base64_encode(const Bytes& bytes) {
    DWORD n=0;CryptBinaryToStringA(bytes.data(),DWORD(bytes.size()),CRYPT_STRING_BASE64|CRYPT_STRING_NOCRLF,nullptr,&n);
    std::string out(n,'\0');if(!CryptBinaryToStringA(bytes.data(),DWORD(bytes.size()),CRYPT_STRING_BASE64|CRYPT_STRING_NOCRLF,out.data(),&n))fail("密钥文件编码失败。");
    out.resize(n);while(!out.empty()&&out.back()==0)out.pop_back();return out;
}
Bytes base64_decode(const std::string& s) {
    if(s.empty()||s.size()%4)fail("本地密钥文件编码损坏。");
    for(char c:s)if(!((c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='+'||c=='/'||c=='='))fail("本地密钥文件编码损坏。");
    DWORD n=0;if(!CryptStringToBinaryA(s.data(),DWORD(s.size()),CRYPT_STRING_BASE64,nullptr,&n,nullptr,nullptr))fail("本地密钥文件编码损坏。");
    Bytes out(n);if(!CryptStringToBinaryA(s.data(),DWORD(s.size()),CRYPT_STRING_BASE64,out.data(),&n,nullptr,nullptr))fail("本地密钥文件编码损坏。");out.resize(n);return out;
}
fs::path key_path() {
    std::vector<wchar_t> path(32768);DWORD n=GetModuleFileNameW(nullptr,path.data(),DWORD(path.size()));
    if(n==0||n>=path.size())fail("无法确定程序目录。");
    return fs::path(std::wstring(path.data(),n)).parent_path()/L"binary_passcode_terminal.key";
}
std::optional<std::string> read_key_file() {
    auto path=key_path();
    if(GetFileAttributesW(path.c_str())==INVALID_FILE_ATTRIBUTES&&GetLastError()==ERROR_FILE_NOT_FOUND) {
        auto legacy=path.parent_path()/L"decimal_cipher_200.key";
        if(GetFileAttributesW(legacy.c_str())!=INVALID_FILE_ATTRIBUTES&&!MoveFileExW(legacy.c_str(),path.c_str(),MOVEFILE_WRITE_THROUGH))fail("旧密钥文件迁移失败，请检查目录权限。");
    }
    HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE){if(GetLastError()==ERROR_FILE_NOT_FOUND)return std::nullopt;fail("无法读取本地密钥文件。");}
    LARGE_INTEGER size{};if(!GetFileSizeEx(file,&size)||size.QuadPart<0||size.QuadPart>65536){CloseHandle(file);fail("密钥文件大小无效。");}
    std::string data(size_t(size.QuadPart),'\0');DWORD used=0;
    BOOL ok=ReadFile(file,data.data(),DWORD(data.size()),&used,nullptr);CloseHandle(file);
    if(!ok||used!=data.size())fail("读取本地密钥文件失败。");return data;
}
void store_key(const std::string& key) {
    check_key(key);Bytes plain(key.begin(),key.end());std::string data=KEY_MAGIC+base64_encode(dpapi(plain));
    auto path=key_path();auto temporary=path;auto suffix=random_bytes(8);
    std::wstring tail=L".tmp-";for(auto b:suffix){tail+=wchar_t(L'a'+(b>>4));tail+=wchar_t(L'a'+(b&15));}temporary+=tail;
    HANDLE file=CreateFileW(temporary.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE)fail("无法保存密钥，请检查程序目录写入权限。");
    DWORD used=0;BOOL ok=WriteFile(file,data.data(),DWORD(data.size()),&used,nullptr);
    if(ok)ok=FlushFileBuffers(file);CloseHandle(file);
    if(!ok||used!=data.size()||!MoveFileExW(temporary.c_str(),path.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)){
        DeleteFileW(temporary.c_str());fail("密钥保存失败，原文件未被主动删除。");
    }
}
std::optional<std::string> load_key() {
    auto data=read_key_file();if(!data)return std::nullopt;
    if(data->size()==128&&digits(*data)){store_key(*data);return *data;}
    if(data->compare(0,KEY_MAGIC.size(),KEY_MAGIC)!=0)fail("密钥文件格式不正确，请重新导入。");
    auto bytes=dpapi(base64_decode(data->substr(KEY_MAGIC.size())),true);
    std::string key(bytes.begin(),bytes.end());check_key(key);return key;
}
#else
struct ToolResult {int status;std::string output;};
ToolResult secret_tool(const std::vector<std::string>& args,const std::string& input="") {
    int in[2],out[2];if(pipe(in))fail("创建密钥环通信管道失败。");
    if(pipe(out)){close(in[0]);close(in[1]);fail("创建密钥环通信管道失败。");}
    pid_t child=fork();
    if(child<0){for(int fd:{in[0],in[1],out[0],out[1]})close(fd);fail("启动密钥环工具失败。");}
    if(child==0){dup2(in[0],STDIN_FILENO);dup2(out[1],STDOUT_FILENO);dup2(out[1],STDERR_FILENO);for(int fd:{in[0],in[1],out[0],out[1]})close(fd);
        std::vector<char*> argv;argv.push_back(const_cast<char*>("secret-tool"));for(auto& arg:args)argv.push_back(const_cast<char*>(arg.c_str()));argv.push_back(nullptr);execvp("secret-tool",argv.data());_exit(127);}
    close(in[0]);close(out[1]);size_t sent=0;
    while(sent<input.size()){ssize_t n=write(in[1],input.data()+sent,input.size()-sent);if(n<0&&errno==EINTR)continue;if(n<=0)break;sent+=size_t(n);}close(in[1]);
    std::string output;char buffer[1024];
    while(true){ssize_t n=read(out[0],buffer,sizeof(buffer));if(n<0&&errno==EINTR)continue;if(n<=0)break;if(output.size()+size_t(n)<=65536)output.append(buffer,size_t(n));}
    close(out[0]);int status=0;while(waitpid(child,&status,0)<0){if(errno!=EINTR)fail("等待密钥环工具失败。");}
    int code=WIFEXITED(status)?WEXITSTATUS(status):128;
    if(code==127)fail("未找到secret-tool，请安装libsecret-tools，并使用已登录的桌面密钥环会话。");
    return {code,output};
}
void store_key(const std::string& key) {
    check_key(key);auto result=secret_tool({"store","--label=Binary Passcode Terminal","application","binary_passcode_terminal","account","default"},key+"\n");
    if(result.status)fail("系统密钥环保存失败，请检查Secret Service是否运行，以及密钥环是否解锁。");
}
std::optional<std::string> load_key() {
    auto result=secret_tool({"lookup","application","binary_passcode_terminal","account","default"});
    bool migrate=result.status==1&&result.output.empty();
    if(migrate){result=secret_tool({"lookup","application","decimal_cipher_200","account","default"});if(result.status==1&&result.output.empty())return std::nullopt;}
    if(result.status)fail("系统密钥环读取失败，请检查桌面会话及密钥环解锁状态。");
    while(!result.output.empty()&&(result.output.back()=='\n'||result.output.back()=='\r'))result.output.pop_back();
    check_key(result.output);if(migrate)store_key(result.output);return result.output;
}
#endif

std::string require_key() {auto key=load_key();if(!key)fail("尚未配置密钥，请先进入3密钥管理导入或生成。");return *key;}
std::string input(const std::string& prompt) {
    std::cout<<prompt<<std::flush;std::string line;if(!std::getline(std::cin,line))throw std::ios_base::failure("EOF");
    if(!line.empty()&&line.back()=='\r')line.pop_back();return line;
}
void key_menu() {
    std::cout<<"\n密钥管理\n";
#ifdef _WIN32
    std::cout<<"本地密钥使用本机账户加密保护。\n";
#else
    std::cout<<"本地密钥使用系统密钥环保存。\n";
#endif
    std::cout<<"\n更换密钥前可选择4显示并备份旧密钥。\n";
    while(true)try {
        std::cout<<"\n1 查看密钥状态\n2 导入或更新密钥\n3 随机生成并保存新密钥\n4 显示当前密钥\n0 返回主菜单\n";
        auto action=input("请选择：");if(action=="0")return;
        if(action=="1")std::cout<<(load_key()?"已配置有效的本机受保护密钥。":"尚未配置密钥。")<<"\n";
        else if(action=="2"){store_key(input("请输入128位半角十进制密钥："));std::cout<<"密钥已更新。\n";}
        else if(action=="3"){store_key(generate_key());std::cout<<"新密钥已生成并保存。需要传递时请选择4显示。\n";}
        else if(action=="4")std::cout<<require_key()<<"\n";
        else std::cout<<"错误：请选择0—4。\n";
    }catch(const std::ios_base::failure&){throw;}catch(const std::exception& e){std::cout<<"错误："<<e.what()<<"\n";}
}

// Line-based interoperability test interface; secrets are read from stdin, not command arguments.
int test_io() {
    auto command=input("");
    if(command=="encode") {auto u=logical_units(input(""));for(size_t i=0;i<u.size();++i)std::cout<<(i?",":"")<<u[i];std::cout<<"\n";}
    else if(command=="decode") {std::string s=input("");Units u;size_t start=0;while(start<s.size()){size_t end=s.find(',',start);u.push_back(std::stoi(s.substr(start,end-start)));if(end==std::string::npos)break;start=end+1;}std::cout<<decode_units(u)<<"\n";}
    else if(command=="encrypt"){auto key=input(""),text=input(""),day=input(""),nonce=input("");std::cout<<encrypt(text,key,day,nonce)<<"\n";}
    else if(command=="decrypt"){auto key=input(""),cipher=input("");std::cout<<decrypt(cipher,key)<<"\n";}
    else if(command=="decrypt-time"){auto key=input(""),cipher=input("");auto result=decrypt_with_time(cipher,key);std::cout<<result.first<<"\n"<<result.second<<"\n";}
    else if(command=="save-key"){store_key(input(""));std::cout<<"OK\n";}
    else if(command=="load-key"){std::cout<<require_key()<<"\n";}
    else fail("未知测试操作。");return 0;
}
int main(int argc,char** argv) {
#ifdef _WIN32
    SetConsoleCP(CP_UTF8);SetConsoleOutputCP(CP_UTF8);
#else
    signal(SIGPIPE,SIG_IGN);
#endif
    try {
        if(argc==2&&std::string(argv[1])=="--test-io")return test_io();
        std::cout<<"二进制密码转换终端 V1.1\n";
        while(true)try {
            std::cout<<"\n1 加密正文\n2 解密密文\n3 密钥管理\n0 退出程序\n";
            auto action=input("请选择：");if(action=="0")break;
            if(action=="1") {
                auto key=require_key();
                std::cout<<"支持大小写英文字母、半角数字、空格、英文句号和逗号、反斜杠、竖线。\n还支持BMP范围内的其他文字和符号，包括全角标点、@#$^&及引号等。\n不支持代理码点及补充平面字符（如部分表情和生僻字）。\n使用基础短编码的其他半角符号："<<SYMBOLS<<"\n最多输入100字符且总容量不超过100单元；扩展字符各占6单元，混合输入可能额外占用容量。\n";
                auto text=input("请输入正文：");std::cout<<"加密结果：\n"<<encrypt(text,key)<<"\n";
            } else if(action=="2") {
                auto key=require_key();auto cipher=input("请输入恰好200位密文：");auto result=decrypt_with_time(cipher,key);
                std::cout<<"生成时间（北京时间）："<<result.first<<"\n解密结果："<<result.second<<"\n";
            } else if(action=="3")key_menu();else std::cout<<"错误：请选择0—3。\n";
        }catch(const std::ios_base::failure&){throw;}catch(const std::exception& e){std::cout<<"错误："<<e.what()<<"\n";}
    }catch(const std::ios_base::failure&){std::cout<<"\n程序已退出。\n";return 0;}
    catch(const std::exception& e){std::cerr<<"错误："<<e.what()<<"\n";return 1;}
    return 0;
}
#else
// Android reuses the same codec, time arithmetic, mask construction and envelope.
// Cryptographic primitives are supplied by the platform Java security providers.
struct AndroidCall {
    AndroidCall(JNIEnv* env,jclass bridge){android_env=env;android_bridge=bridge;}
    ~AndroidCall(){android_env=nullptr;android_bridge=nullptr;}
};
std::string android_string(JNIEnv* env,jstring value) {
    if(!value)fail("输入不能为空。");
    jsize size=env->GetStringLength(value);const jchar* chars=env->GetStringChars(value,nullptr);
    if(!chars)fail("无法读取输入。");
    std::u32string text;text.reserve(size);
    // Copy before performing validation so UTF-16 storage is always released.
    for(jsize i=0;i<size;++i)text.push_back(chars[i]);
    env->ReleaseStringChars(value,chars);
    for(auto c:text)if(c>=0xd800&&c<=0xdfff)fail("不支持代理码点及补充平面字符，请使用BMP范围内的字符。");
    return utf8_encode(text);
}
jstring android_string(JNIEnv* env,const std::string& value) {
    auto text=utf8_decode(value);std::vector<jchar> chars;chars.reserve(text.size());
    for(auto c:text){if(c>0xffff)fail("输出字符超出BMP范围。");chars.push_back(jchar(c));}
    const jchar empty=0;return env->NewString(chars.empty()?&empty:chars.data(),jsize(chars.size()));
}
void android_error(JNIEnv* env,const std::exception& error) {
    if(env->ExceptionCheck())return;
    auto type=env->FindClass("java/lang/IllegalArgumentException");
    if(type){env->ThrowNew(type,error.what());env->DeleteLocalRef(type);}
}
extern "C" JNIEXPORT jstring JNICALL Java_org_binarypasscode_terminal_NativeBridge_encrypt(JNIEnv* env,jclass bridge,jstring text,jstring key) {
    AndroidCall call(env,bridge);
    try{return android_string(env,encrypt(android_string(env,text),android_string(env,key)));}
    catch(const std::exception& e){android_error(env,e);return nullptr;}
}
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_binarypasscode_terminal_NativeBridge_decrypt(JNIEnv* env,jclass bridge,jstring cipher,jstring key) {
    AndroidCall call(env,bridge);
    try{
        auto result=decrypt_with_time(android_string(env,cipher),android_string(env,key));
        auto type=env->FindClass("java/lang/String");if(!type)return nullptr;
        auto array=env->NewObjectArray(2,type,nullptr);env->DeleteLocalRef(type);if(!array)return nullptr;
        auto time=android_string(env,result.first),text=android_string(env,result.second);
        if(!time||!text)return nullptr;
        env->SetObjectArrayElement(array,0,time);env->SetObjectArrayElement(array,1,text);
        env->DeleteLocalRef(time);env->DeleteLocalRef(text);return array;
    }catch(const std::exception& e){android_error(env,e);return nullptr;}
}
extern "C" JNIEXPORT jstring JNICALL Java_org_binarypasscode_terminal_NativeBridge_generateKey(JNIEnv* env,jclass bridge) {
    AndroidCall call(env,bridge);
    try{return android_string(env,generate_key());}catch(const std::exception& e){android_error(env,e);return nullptr;}
}
#endif
