#include "PixelCodec.hpp"
#define STB_IMAGE_IMPLEMENTATION
#define STBI_NO_STDIO
#define STBI_NO_HDR
#define STBI_NO_LINEAR
#define STBI_ONLY_PNG
#define STBI_ONLY_JPEG
#define STBI_ONLY_BMP
#define STBI_MAX_DIMENSIONS 20000
#include "../Vendor/stb_image.h"
#define STB_IMAGE_WRITE_IMPLEMENTATION
#define STBI_WRITE_NO_STDIO
#include "../Vendor/stb_image_write.h"
#include <memory>
namespace bip {
Pixels loadPixels(const Bytes& data,int desired){
    int w=0,h=0,c=0;
    if(data.empty()||data.size()>150*1024*1024||!stbi_info_from_memory(data.data(),int(data.size()),&w,&h,&c)||w<1||h<1||int64_t(w)*h>80000000||std::max(w,h)>20000)throw Error("图片无法读取或尺寸过大。最多8,000万像素，单边20,000，文件150 MiB。");
    std::unique_ptr<stbi_uc,decltype(&stbi_image_free)> p(stbi_load_from_memory(data.data(),int(data.size()),&w,&h,&c,desired),stbi_image_free);
    if(!p)throw Error("无法读取完整图片。");
    return {w,h,desired,Bytes(p.get(),p.get()+size_t(w)*h*desired)};
}
static void append(void* context,void* data,int length){auto out=static_cast<Bytes*>(context);auto p=static_cast<uint8_t*>(data);out->insert(out->end(),p,p+length);}
Bytes writePNG(const Pixels& p){Bytes out;if((p.channels!=3&&p.channels!=4)||p.data.size()!=size_t(p.w)*p.h*p.channels||!stbi_write_png_to_func(append,&out,p.w,p.h,p.channels,p.data.data(),p.w*p.channels))throw Error("PNG保存失败。");return out;}
}
