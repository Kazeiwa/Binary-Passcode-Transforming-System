#pragma once
#include <cstdint>
#include <functional>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace bip {
using Bytes = std::vector<uint8_t>;
using Progress = std::function<void(int, const std::string&)>;
struct Error : std::runtime_error { using runtime_error::runtime_error; };
struct Image {
    int w=0,h=0;
    Bytes rgb;
    Image()=default;
    Image(int width,int height,Bytes data);
    int bit(int x,int y,int channel) const;
    void bit(int x,int y,int channel,int value);
    Image rotated() const;
};
struct Prepared { Bytes data; int w=0,h=0,quality=0; bool png=false; };
struct Result {
    std::u16string text;
    Prepared image;
    uint64_t seconds=0;
    int used=0,recovered=0,total=0,required=0,corrected=0,rotation=0;
};
struct Layout { int n,k,size,mx,my; std::vector<std::pair<int,int>> origins; };
extern const char* AUTH;
void validateKey(const std::string&);
std::string generateKey();
std::vector<int> units(const std::u16string&);
Bytes sealText(const std::u16string&,const std::string&,uint64_t,const Bytes&);
Result openText(const Bytes&,const std::string&);
Bytes sealImage(const Prepared&,const std::string&,uint64_t,const Bytes&);
Result openImage(const Bytes&,const std::string&);
Layout layout(int,int,bool,size_t=37595);
int jpegCapacity(int,int,bool);
int denseCapacity(int,int);
void encode(Image&,const Bytes&,const std::string&,bool,bool,const Progress& = {});
Result decode(const Image&,const std::string&,const Progress& = {});
Bytes randomBytes(size_t);
Bytes hmac(const Bytes&,const Bytes&);
Bytes aes(bool,const Bytes&,const Bytes&,const Bytes&,const Bytes&);
Bytes shake(const Bytes&,size_t);
Bytes rsEncode(const Bytes&);
Bytes rsDecode(const Bytes&,int&);
}
