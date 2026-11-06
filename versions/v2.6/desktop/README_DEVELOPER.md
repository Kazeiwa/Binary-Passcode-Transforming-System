# V2.6 开发说明

V2.6保留文字与JPG图片功能，增加双预览、RGBA PNG无损正文，以及高容量完整文件传输。基础说明见[V2.5开发说明](README_DEVELOPER_V2.5.md)与[V2.1文字协议](README_DEVELOPER_V2.1.md)。

## 图片封装扩展

`PreparedImage`新增`format`字段，默认`JPEG`；PNG为`format='PNG',quality=0`。加密元数据`>HHBBI`中的kind取1表示JPEG、2表示PNG。最大PNG文件9,000,000字节，图片仍在1920×1080/1080×1920包围盒内。

图片信封的61字节头部、AEAD、时间和用途派生域保持原定义；PNG/JPG均通过新随机48字节nonce派生密钥。PNG无损仍使用完整消息AES-GCM认证。新增`DecodeResult.image_format`，默认JPEG，PNG返回PNG；不要以扩展名猜测认证后的消息类型。

`prepare_image(...,lossless=True)`在1080P适配后保留8位RGB/RGBA像素，保留alpha，以PNG压缩级别9保存，不做JPEG量化。空间不足直接报错，不再次缩小。`encode_image_file(...,lossless=True)`选择新的高容量传输层；`save_image_result`按认证结果限制.png或.jpg/.jpeg。

## dense_transport.py

PNG无损不使用原196块擦除配置，以允许数MiB正文。其设计明确要求完整文件，不提供裁剪恢复或数据纠错；可尝试四个90°方向。整个载荷受AEAD认证，任何未被重复头恢复的错误都导致拒绝，不能输出部分图像。

四边固定留白4%，`mx=ceil(W*.04),my=ceil(H*.04)`，内部矩形按行优先RGB槽位编号。头部`>4sBBBB48sI`为60字节：

```text
magic=BIPD
version=1, profile=4, flags=0, reserved=0
nonce:48字节
total:4字节大端，实际图片信封长度
```

头部后加32字节HMAC-SHA256，密钥为现有图片HKDF函数的`dense-header`用途。这个92字节认证头重复3次，独立验证，要求所有验证成功的副本参数一致。共占2208个比特槽位。完整秘密内容仍在AEAD信封内；头部长度与nonce可见。

正文从剩余槽位中通过一一映射取位置：

```text
seed=HMAC(derive(key,'dense-positions',nonce),b'positions')
start=int_be(seed[:8]) mod M
step=int_be(seed[8:16]) mod M，调整至与M互质，且非0
position(i)=2208+(start+step*i) mod M
```

M为内部槽位数减2208。该排列只安排位置，保密性依赖AEAD，不宣称排列本身是密码学安全的均匀随机洗牌。实现按262144比特分批读写，避免为整个数千万像素载体同时分配全部索引。

最多可容纳的PNG字节数：

```text
min(9000000, floor((innerW*innerH*3-2208)/8)-87)
```

87是图片信封开销。建议方形底图通过容量函数精确搜索，考虑留白向上取整，不能仅根据面积近似值宣称一定容纳。PNG接口本身不要求原文字最小块布局，文件读取仍保留载体80MP、单边20,000和150MiB限制。

解码先尝试密集传输的三份认证头和四个方向；没有匹配魔数时继续原文字/JPG解码。发现密集头但无法认证时拒绝。认证头长度检查及容量检查在读正文前执行，最大读取受9MB资源边界限制；AEAD通过后再验证PNG真实格式、尺寸、颜色模式和实际解码。

## 双预览

GUI分别保存底图PhotoImage与密图PhotoImage，右侧使用等权uniform网格，避免自然图片请求尺寸挤掉另一份预览。小预览透明度铺白仅用于显示，不修改PNG正文。双击打开独立预览窗口。

选择秘密图片后通过后台任务生成1080P适配预览，完成加密后显示实际JPEG或PNG正文。解密时保留底图，另显示认证后的密图。清除结果只移除密图数据及显示，不清除已选底图。PNG选择禁用裁剪冗余控件，切回文字/JPG恢复选择。

## 测试与构建

```powershell
python -m pip install -r requirements-dev.txt
$env:BIP_RUN_LARGE='1'
python -m pytest tests -q
python -m pip install pyinstaller
python build_windows.py
```

测试包括逐像素RGBA透明度、PNG输出字节一致、完整1080P高噪声图片与4800方图真实往返、头部副本损坏、正文损坏拒绝、旋转、裁剪反例、空间不足不偷偷缩小、双预览与PNG保存。Windows独立EXE还须验证`--lossless`命令及真实RGBA输出。详见[测试报告](docs/TEST_REPORT.md)。
