# V2.5 开发补充说明

本文定义V2.5新增的JPEG图片正文。完整的文字编码、V2.1信封、RGB槽位、局部定位、RS、GF(256)擦除码及密钥库说明见 [V2.1协议参考](README_DEVELOPER_V2.1.md)。V2.5保留这些文字行为；旧参考中的软件版本和固定信封长度仅适用于文字正文。

## 模块

- `bip/image_payload.py`：图片预处理、容量适配、JPEG、图片AEAD信封、图片消息文件入口及JPG输出。
- `bip/image_transport.py`：扩展为按头部识别文字/图片线格式，允许图片信封长度变化；文字默认参数保持不变。
- `bip/gui.py`：加密页文字/图片选择，解密自动类型识别、JPG预览及保存，结果清理与控件状态。
- `binary_image_passcode.py`：增加`encode-image`，解密图片时要求JPG输出路径。

## 容量和压缩

秘密图片先做EXIF方向校正，再以1920×1080或1080×1920为包围盒等比缩小，不放大。支持至多2,073,600像素，长边≤1920、短边≤1080。透明铺白，转换RGB，重新保存JPEG，不保留源文件EXIF等元数据。

JPEG编码使用Pillow，`optimize=True,subsampling=2`，质量按85、80、75、70、65、60、55、50尝试；均超出预算则宽高各取85%（整数向下，至少1），然后重新尝试上述质量序列。

`MAX_JPEG_BYTES=512000` 是协议解析资源上界。实际预算还受载体k值约束，取`min(512000,k*5140-87)`。5140为当前块结构能容纳的最大shard字节数，87为图片信封的固定开销。均衡1024方图约能容纳128,413字节JPEG；增强约87,293字节。维持现有MAX_SHARDS=196时，均衡最大实际预算503,633字节，增强339,153字节。

最小编码载体、留白和k/n规则沿用既有图像层。JPEG质量自适应以保持容量可行，不能同时保证所有输入都保持1080P尺寸和固定画质。秘密图片不套用载体的80MP/单边20,000限制。仅打开秘密图片头部时临时解除Pillow通用像素阈值，之后立即恢复；读取EXIF方向，JPEG先draft降采样，按可用物理内存估算解码预算，再thumbnail缩至目标框。仍限制文件150MiB，并拒绝多帧图像。PNG等格式可能需要解码完整原始像素，不能承诺超出设备内存的输入仍能成功。

## 图片信封

图片使用独立线格式，软件版本2.5.0不等于线格式VERSION：

```text
信封头 >4sBBBB48s5s，共61字节：
  magic=BIP3, version=3, codec=2, profile=3, flags=0
  nonce=48随机字节
  encrypted_time=5字节大端整数

加密明文 >HHBBI + JPEG：
  width:uint16, height:uint16, quality:uint8, kind:uint8(1=JPEG)
  jpeg_size:uint32, jpeg_bytes

AES-GCM认证标签：16字节，由encrypt接口追加
总长度=61+10+jpeg_size+16=87+jpeg_size
```

所有整数大端。图片信封不使用文字的两字节单元数、空格填充或37,500字节固定正文，也不使用原文字HMAC掩码。因此不受原两字节掩码计数器限制。

图片HKDF-SHA256输入仍为128位数字的ASCII字节，salt为本消息48字节nonce，长度32，info域为`binary_image_passcode/v2.5/`加用途标签：

```text
image-time → 时间偏移密钥
image-body → AES-256-GCM密钥
image-iv   → GCM IV派生密钥
```

时间沿用UTC 1970起秒数T和范围[0,10^10)，无时区datetime按北京时间解释。`O=int_be(HMAC(image-time-key,b'seconds')) mod 10^10`，头部E=(T+O) mod 10^10。GCM IV为`HMAC(image-iv-key,b'jpeg')[:12]`；61字节原始头部作为AAD。每次加密随机48字节nonce，进而派生新的密钥和IV。固定nonce参数仅供测试，不应在生产中复用。

先完成GCM认证，再检查头部、时间、明文参数和JPEG内容。检查尺寸、资源上界、JPEG真实格式及尺寸一致性，最后实际解码JPEG以拒绝损坏数据。所有失败都不向GUI输出未经验证的图片字节。

## 图像传输扩展

保持既有66字节包头、98字节RS前缀、三点定位、SHAKE位置排列、块HMAC、内层RS与外层擦除矩阵。传输头的(version,profile,codec)为(3,3,2)，文字仍为(2,2,1)。total变为实际图片信封长度，size=ceil(total/k)。

文字和图片使用相同的、基于通信密钥的前缀位置，才能在未知类型和nonce时读取块头。包认证及正文槽位沿用既有图像层的用途派生域；其认证包含不同的版本/类型及总长度。图片信封自身使用上面独立的V2.5域。

解码验证头部范围后读取有界正文，RS及包HMAC成功后才入组。组标识扩充为`(nonce,k,n,size,total,wire)`；满足门限恢复信封后，按wire选择原文字认证解码或新JPEG AEAD解码。信封nonce必须与分组一致。

`DecodeResult`增加默认None字段`image_bytes,image_size,jpeg_quality`。文字仍有text；图片text为空、used_units为0、message_format为2.5。GUI和CLI必须检查`image_bytes`区分内容，不能将二进制塞入文本控件或stdout。

## API

```python
prepare_image(source, max_bytes=512000, cancel=None, progress=None)
# PreparedImage(data,width,height,quality,original_size)

jpeg_capacity(width,height,strength='balanced')
# 当前载体可用JPEG字节预算

seal_image(image,key,when=None,nonce=None)
open_image(envelope,key)

encode_image_file(carrier,target,secret,key,strength='balanced',
                  overwrite=False,cancel=None,progress=None,when=None)
# ImageEncodeResult(layout,output_path,image,message_id)

save_image_result(result,target,overwrite=False,protected_paths=())
```

`plan_layout`增加可选`envelope_bytes`，默认为文字原固定长度；`encode_array`内部参数`_envelope`用于注入已经认证封装的JPEG信封，前端优先使用`encode_image_file`。两类消息共用原子PNG保存函数`save_png`。

JPG输出直接原子写出已认证的JPEG字节，不二次压缩。输出扩展名限.jpg/.jpeg，拒绝覆盖受保护的原始载体/秘密图片路径。两种消息均以PNG载体发送。

## GUI与兼容

继续使用原密钥库路径、保护后端、备份格式和文字协议。新增消息内容单选入口，压缩结果显示尺寸、大小和质量参数；解密图片后禁用复制/保存正文，启用JPG保存。更换输入、选择其他密钥、开始新解密或锁定时清除图片字节和预览。

新图片消息需要V2.5解码器；V2.1及安卓首发版只能继续交换文字消息。现有兼容读取模块保持隔离。界面只显示秒级北京时间；较旧的分钟精度历史消息仍按实际精度显示。

## 测试与构建

运行依赖不增加。开发测试与Windows构建：

```powershell
python -m pip install -r requirements-dev.txt
$env:BIP_RUN_LARGE='1'
python -m pytest tests -q
python -m pip install pyinstaller
python build_windows.py
```

新增图片测试覆盖格式转换、透明底色、横竖适配、噪声图容量压缩、时间边界、认证篡改、错误密钥、最小载体、不同冗余、旋转裁剪和原文件保护。Windows Tk图片流程使用子进程隔离GUI根解释器，在920×680和1140×800验证控件与往返保存。

版本2.5的Windows发布物另需实际验证冻结EXE的图片命令、文字命令、旧图读取、DPAPI库和GUI启动，不以源码测试代替冻结程序测试。结果见[测试报告](docs/TEST_REPORT.md)。
