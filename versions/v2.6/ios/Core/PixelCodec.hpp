#pragma once
#include "BIPCore.hpp"
namespace bip {
struct Pixels { int w,h,channels; Bytes data; };
Pixels loadPixels(const Bytes&,int desired=3);
Bytes writePNG(const Pixels&);
}
