#include "../Core/PixelCodec.hpp"
#include <fstream>
#include <iostream>
int main(int argc,char** argv){try{if(argc!=4)throw bip::Error("input channels output");std::ifstream f(argv[1],std::ios::binary);bip::Bytes data(std::istreambuf_iterator<char>(f),{});auto p=bip::loadPixels(data,std::stoi(argv[2]));auto png=bip::writePNG(p);auto again=bip::loadPixels(png,p.channels);if(again.w!=p.w||again.h!=p.h||again.data!=p.data)throw bip::Error("pixel mismatch");std::ofstream out(argv[3],std::ios::binary);out.write(reinterpret_cast<const char*>(png.data()),png.size());std::cout<<p.w<<" "<<p.h;return 0;}catch(const std::exception& e){std::cerr<<e.what();return 1;}}
