# binary_image_passcode · 二进制密码转换终端 · 图片版 V2.6

将文字或图片加密后写入另一张图片，通过PNG文件传递，再由持有相同密钥的接收者还原。

支持 **Windows、Linux、Android、iOS / iPadOS** 四端，使用兼容的V2.6消息格式。本文面向首次使用的用户与开发者，无需了解以前版本；先介绍安装和使用，再介绍协议、源码与构建。

## 1. 功能概览

- **文字消息**：英文、数字、标点及Unicode BMP字符，支持常用简繁中文、日文假名和韩文；保留输入的换行和末尾空格。
- **图片消息**：JPG压缩和PNG像素无损两种模式，正文图片等比例适配至1080P范围。
- **像素嵌入**：RGB三个通道的最低位分别传输数据，对外输出统一为PNG。
- **认证后解密**：消息通过完整性和密钥认证后，才显示正文或还原图片。
- **双图预览**：同时查看载体和需要隐藏或已经还原的图片正文。
- **秒级时间**：加密保存生成时间，解密后显示北京时间，精确到秒。
- **多密钥管理**：生成、导入、选用、查看、删除和加密备份，操作细节以各端界面为准。
- **有限裁剪恢复**：文字与JPG采用冗余分块，剩余有效块足够时可以恢复。

V2.6主要增加PNG无损正文、高容量图片传输和双图预览，并已提供四端实现。iOS界面另有相册/文件双来源、图片默认保存相册、保存结果反馈、键盘收起和独立的加密/解密图片状态。

## 2. 基本概念

| 名称 | 含义 |
| --- | --- |
| 正文 | 真正需要传递的文字或图片 |
| 底图 / 载体 | 承载消息、对方直接看到的图片 |
| 密文PNG | 写入加密数据后的载体，是需要发送的文件 |
| 通信密钥 | 双方持有的同一串128位半角数字 |
| 密钥库 | 本机保存和管理通信密钥的位置 |
| 主密码 / 备份密码 | 保护密钥库或备份文件的密码，与通信密钥不同 |

图片模式需要底图和图片正文两张图片。**JPG或PNG是正文格式的选择；实际发送的加密载体始终是PNG。**

## 3. 平台支持与安装

| 平台 | 运行形式 | 要求 |
| --- | --- | --- |
| Windows | 独立EXE或Python源码 | EXE无需Python；源码需要Python 3.11+、Tk和依赖 |
| Linux | `tar.gz`源码启动包，GUI与CLI | Python 3.11+；GUI需要Tk与桌面环境，脚本自动建立虚拟环境 |
| Android | 原生Java应用，APK | Android 8.0及以上，无需Python |
| iOS / iPadOS | SwiftUI原生应用，IPA | iOS / iPadOS 16及以上，安装包需适当签名，无需Python |

最低版本来自工程配置。大图片的实际处理能力还取决于设备内存和系统解码器，各端界面和保存方式不完全相同。

### Windows

解压Windows发布包，运行`binary_image_passcode.exe`。程序文件与密钥库分开保存，升级前请导出密钥备份。

运行Python源码：

```powershell
python -m pip install -r requirements.txt
python binary_image_passcode.py
```

### Linux

```bash
tar -xzf binary_image_passcode_v2.6_linux.tar.gz
cd binary_image_passcode_v2.6_linux
./run_linux.sh
```

脚本使用系统Python创建本目录的`.venv`，首次安装依赖，然后启动程序。首次安装依赖需要联网，后续消息处理在本机完成。**此包不附带Python解释器，不是免运行环境的单文件二进制程序。**

如缺少Tk、虚拟环境或密钥环工具，可通过发行版包管理器安装。Debian / Ubuntu示例：

```bash
sudo apt-get update
sudo apt-get install python3 python3-tk python3-venv libsecret-tools
```

Python仍须达到3.11。可指定其他已安装的解释器：

```bash
BIP_PYTHON=python3.12 ./run_linux.sh
```

`libsecret-tools`用于系统密钥环，也可选择主密码保护。GUI需要显示环境；通过启动脚本传入CLI子命令时不强制检查Tk。

### Android

安装发布的APK，按系统提示完成安装。首次在密钥管理中生成或导入通信密钥。覆盖升级通常需要保持相同的包名和签名证书；卸载、清除数据或换机前先备份。

### iOS / iPadOS

通过适用签名渠道安装IPA。未签名IPA只是构建产物，不能直接安装；可使用自己的开发签名、适用的侧载工具或其他分发方式，限制取决于账户和安装方式。

源码构建需要Mac上的Xcode，或云端macOS构建机。Windows用户也可将源码交给GitHub Actions构建，详见开发部分。

## 4. 第一次使用

1. 打开密钥管理，生成通信密钥，或导入对方提供的密钥。
2. 密钥必须为**恰好128位半角数字**，允许前导零；不要按整数处理。
3. 命名并选用。双方名称不必相同，数字内容必须完全一致。
4. 通过双方信任的方式把密钥交给接收者，在接收端按原样保存。
5. 导出带密码的密钥备份，单独保管备份密码。

“128位数字”指128个十进制字符，不是128 bit。默认生成器使用安全随机数；手工填写易猜或重复的数字，不会仅因长度足够而自动可靠。

## 5. 加密与解密

### 文字

在加密页选用密钥，选择底图，将正文类型设为文字，输入正文，按需选择均衡或增强裁剪恢复，执行加密后保存密文PNG。

上限是**60,000个五位编码单元**，不是任意60,000个字符。小写英文字母通常占一个单元，大小写/数字模式切换也占单元；常用中文等扩展字符通常每字6单元。纯扩展字符正文约可容纳10,000个字符，混排以界面显示的单元数为准。

目前不支持BMP之外的补充平面字符，例如许多表情和部分罕见汉字。不支持的字符或超限输入会报错。

### 图片

选择底图，将正文类型设为图片，再选择需要隐藏的图片，检查双图预览，选择JPG或PNG无损模式，执行加密并保存载体。

| 项目 | JPG压缩，默认 | PNG无损 |
| --- | --- | --- |
| 正文格式 | JPEG | PNG |
| 初始尺寸 | 等比例适配至长边1920、短边1080以内，不放大小图 | 相同 |
| 容量不足 | 降低质量，必要时继续缩小正文 | 报错并要求更大底图，不为适应容量继续缩小 |
| 透明区域 | 合成白底 | 保留 |
| 裁剪恢复 | 均衡或增强冗余 | 不支持，需要完整载体 |
| 解密输出 | JPG | PNG |
| 适用内容 | 照片、节省空间 | 截图、图标、线稿及保留像素细节 |

**PNG无损指尺寸与颜色适配后的8位RGB/RGBA像素无损，不是原始文件逐字节备份。** 大图仍会先缩小，方向和颜色模式会规范化，原文件元数据不保证保留。各平台压缩器产生的文件字节可能不同，不影响协议互通。

正文图片可从较大分辨率输入，但仍受文件大小、解码器和内存限制。PNG、JPG之外的BMP、WebP、TIFF、HEIF等格式，能否直接使用取决于平台支持；不支持时先导出静态PNG或JPG。不要对密文载体做这种格式转换。

### 解密与时间

在解密页选择相同密钥和收到的密文PNG，执行解密。程序自动识别消息类型，认证通过后显示、复制或保存结果。

生成时间取自发送设备时钟，按北京时间显示到秒，不显示数值时间戳。它不是可信授时证明，也不具备防重放作用。

### iOS交互

- 底图、正文图片和待解密图片均可从相册或文件选择。
- 加密密文PNG和解密图片默认保存到系统相册，同时保留另存文件。
- 保存期间显示进度，成功弹窗确认；权限不足或保存失败会显示原因。
- 仅申请添加照片权限，保存按图片资源字节写入，不经UIImage重新编码。
- 文字输入框提供“收起键盘”；加密与解密分别保留各自载体。
- “刷新密钥列表”重新读取本机钥匙串，单击后显示结果，不会打开其他密钥文件。

其他平台通过各自的系统文件选择器或桌面保存对话框选择保存位置。

## 6. 底图大小与文件传递

| 文字 / JPG模式 | 最低总像素 | 方图参考 | 最短边 |
| --- | ---: | --- | --- |
| 均衡 | 313,600 | 560×560 | 140像素 |
| 增强 | 484,416 | 696×696 | 140像素 |

还需满足完整数据块布局，达到总像素下限不代表任意长宽比都可用。文字推荐1024×1024以上，JPG图片可优先选择1536×1536或2048×2048以上。

PNG无损容量取决于正文PNG压缩后的实际字节数，没有固定的像素数量换算：

| 方形底图 | PNG正文容量，约 |
| --- | ---: |
| 1024×1024 | 325 KiB |
| 1536×1536 | 730 KiB |
| 2048×2048 | 1.27 MiB |
| 4096×4096 | 5.08 MiB |

复杂1080P RGB图片可考虑4800×4800级底图，RGBA可考虑5400×5400级，实际以程序检查为准。载体上限为**8,000万像素、单边20,000像素、文件150 MiB**，不保证所有设备都有足够内存达到上限。

发送时选择文件、原始文件或能保留原始PNG的方式，不要用截图、缩略图或编辑副本代替：

| 操作 | 文字 / JPG消息 | PNG无损消息 |
| --- | --- | --- |
| 像素不变的PNG重新压缩 | 可识别 | 可识别 |
| 90°倍数无插值旋转 | 可识别 | 可识别 |
| 裁剪 | 剩余有效块足够时可恢复 | 不支持 |
| 缩放、滤镜、截图、转JPG | 可能破坏消息，不保证恢复 | 不支持 |

裁剪门槛按有效块计算，不等同于可以任意裁掉某个固定比例的面积。

## 7. 密钥库与跨平台互通

四端互通依赖相同的**通信密钥和消息协议**，不依赖相同的密钥名称或本地密钥库文件。

| 平台 | 本地保护 | 备份 |
| --- | --- | --- |
| Windows | Windows账户DPAPI，或主密码 | 桌面备份机制，密码至少12字符 |
| Linux | Secret Service密钥环，或主密码 | 桌面备份机制，密码至少12字符 |
| Android | Android Keystore保护加密密钥库 | 安卓独立备份格式，密码至少12字符 |
| iOS | 本机系统钥匙串，解锁时可访问 | iOS独立备份格式，密码至少10字符 |

移动端备份容器不等同于桌面备份，安卓与iOS也不是同一备份格式。跨平台迁移可查看并复制原始128位通信密钥，在另一端按原样导入。

桌面默认数据位置：Windows为`%LOCALAPPDATA%\BinaryImagePasscode`，Linux为`${XDG_DATA_HOME:-~/.local/share}/binary_image_passcode`。Android使用应用私有区域，iOS使用钥匙串。不要依赖卸载或清理后的残留数据恢复密钥；升级、换机、删除前先备份。

## 8. 安全边界

本项目结合消息加密认证与图片像素嵌入：加密保护正文，像素嵌入负责数据承载。

- 图片使用AES-256-GCM；文字使用用途隔离的HMAC派生掩码和HMAC-SHA256认证。
- 密钥派生使用HKDF-SHA256，各用途标签独立，每条消息生成新的48字节随机值。
- 认证失败、字段不合法或数据损坏时，不输出未验证正文。
- 公开头部、长度和像素统计可能暴露消息存在或类型，不保证无法检测到隐写载体。
- 使用标准组件不等于整个自定义协议已经通过独立安全审计。

保密性仍依赖密钥质量、密钥分发和终端设备。不要把通信密钥与密文一起发送，作为保密传递方式。

## 9. 开发者：编码与协议

```text
文字 → 五位状态编码 → 固定长度填充 → 加密与认证 ┐
                                               ├→ 像素嵌入 → 密文PNG
图片 → 尺寸/颜色适配 → JPG或PNG → AES-GCM封装 ┘

密文PNG → 定位与读取 → 认证与解密 → 文字解码 / 图片资源
```

图片正文直接封装文件字节，**不使用五位文字编码**。多字节整数为大端序，字节内按最高位优先传输。

### 五位文字编码

| 默认模式单元 | 意义 |
| --- | --- |
| 0—25 | a—z，大写状态下为A—Z |
| 26 | 半角逗号 |
| 27 | 局部符号：默认为反斜杠，大写状态为竖线 |
| 28 | 半角空格 |
| 29 | 小数点 / 英文句号 |
| 30 | 大写状态切换，不要求成对 |
| 31 | 数字模式切换，数字段需闭合 |

数字模式中0—9表示单个数字，其余可用槽位按固定顺序映射以下符号，句号仍使用全局单元29：

```text
+-*/=!%_:;?"<>()[]{}
```

非基础BMP字符使用`[LOCAL, 20, h3, h2, h1, h0]`，后四项为Unicode码值的十六进制数位，共6单元。字面反斜杠后紧邻u时，编码器插入两次状态切换解除歧义，解码后仍保留字面内容。

正文填充至60,000单元，即300,000 bit / 37,500字节，并保存实际使用单元数以保留末尾空格。修改编码表、状态或填充规则会影响兼容性。

### 消息封装

| 类型 | 魔数 | 结构 | 长度 |
| --- | --- | --- | --- |
| 文字 | `BIP2` | 61字节头部、37,502字节加密正文与长度、32字节HMAC | 37,595字节 |
| 图片 | `BIP3` | 61字节头部、10字节图片元数据、文件数据、16字节GCM标签 | 文件长度 + 87字节 |

头部包含格式标识、48字节随机值和5字节加密时间字段。时间原值为Unix秒数，范围0—9,999,999,999，时间和正文一同受认证保护。

图片元数据为`>HHBBI`：宽、高、质量、类型、字节数。类型1为JPEG，2为PNG；PNG质量为0，JPG质量范围50—85。JPG文件最多512,000字节，PNG最多9,000,000字节，另需满足实际载体容量。

为保持互通，V2.6沿用文字派生域`binary_image_passcode/v2.1/`和图片派生域`binary_image_passcode/v2.5/`，不能随界面版本号随意替换。

### 像素传输

RGB通道值最低位分别承载数据，偶数表示0，奇数表示1，每像素最多三个槽位；三通道独立传输，不做多数表决。

**文字/JPG分块传输：** 128×128像素块，带定位标记，最多196块。均衡通常至少保留约一半有效块，增强约三分之一。采用分块认证、纠错与纠删冗余；大图边缘留白约4%—12%。这里不展开纠错算法细节。

**PNG高容量传输：** 固定4%边缘留白，内部RGB槽位按行编号。魔数`BIPD`，单份头部为60字节数据与32字节HMAC，三份共2208个比特槽位。正文位置由密钥派生起点和互质步长排列，保密性来自消息加密，不是位置排列本身。该模式不提供正文纠错或裁剪恢复。

PNG正文容量：

```text
innerW = W - 2 × ceil(0.04 × W)
innerH = H - 2 × ceil(0.04 × H)
capacity = max(0, min(9,000,000,
                     floor((innerW × innerH × 3 - 2208) / 8) - 87))
```

解码尝试四个直角方向，校验头部和长度，再读取、认证、解析正文。不要在认证前把不可信内容交给界面或图片解码器。

## 10. 源码与构建

完整开发目录的主要组件如下。Linux包只包含桌面Python部分，移动端也提供独立源码包。

| 位置 | 职责 |
| --- | --- |
| `binary_image_passcode.py` | Python GUI与CLI入口 |
| `bip/codec.py`、`bip/protocol.py` | 文字编码、消息信封与认证 |
| `bip/image_payload.py` | 图片适配、压缩、AEAD封装 |
| `bip/image_transport.py` | 文字/JPG分块传输 |
| `bip/dense_transport.py` | PNG高容量传输 |
| `bip/vault.py`、`bip/gui.py` | 桌面密钥库与GUI |
| `android/` | 原生Java、APK构建与安卓测试 |
| `ios/` | SwiftUI、Objective-C++桥与C++核心 |
| `tests/` | Python测试 |
| `assets/`、`licenses/` | 资源与第三方许可 |

Python依赖由`requirements.txt`维护：Pillow、NumPy、cryptography、reedsolo。测试另见`requirements-dev.txt`。不要把真实密钥、密钥库、签名证书或带私密信息的样例打进发布包。

### Python与Windows

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
python binary_image_passcode.py
```

GUI测试需要显示环境，大图测试需要足够内存。在Windows打包EXE：

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python build_windows.py
```

Linux源码启动包可在任意具备Python的构建机上生成，不进行ELF交叉编译：

```bash
python build_linux.py --output binary_image_passcode_v2.6_linux.tar.gz
```

打包脚本按明确目录清单收集源码、资源、依赖、许可和测试，排除缓存与虚拟环境，并生成校验清单和可执行的Linux启动脚本。

### Android

需要Python 3、JDK 17+、Android Platform 36和Build Tools 36。在安卓源码目录运行：

```bash
python build_android.py --sdk /path/to/Android/Sdk --work /path/to/build --output binary_image_passcode_v2.6.apk
```

构建器使用AAPT2、javac、D8、zipalign和apksigner，不捆绑Python。请保管签名材料，保证后续更新可覆盖安装。

### iOS

在Mac上的iOS源码目录执行：

```bash
python3 build_ios.py --test
python3 build_ios.py --unsigned
```

有可用团队和签名配置时：

```bash
python3 build_ios.py --team YOUR_TEAM_ID --bundle-id your.unique.binarypasscode --method debugging
```

源码包包含Xcode工程和确定性生成器。模拟器采用本地ad-hoc签名，专用权限不用于真机归档。无Mac可使用随包的GitHub Actions手动工作流。

成功时下载`binary_image_passcode_v2.6_ios_unsigned`；诊断记录为`binary_image_passcode_v2.6_ios_diagnostics`。未签名IPA在`dist/`，仍需签名才能安装。

## 11. Python命令行

在桌面源码目录运行，或把相同子命令传给Linux启动脚本。先通过GUI建立密钥库。

`--key`是**库内名称或ID**，不是原始密钥；省略时使用默认密钥，不通过命令行传递128位原始密钥。

```bash
python binary_image_passcode.py --version
python binary_image_passcode.py capacity cover.png --strength balanced

# 加密UTF-8文字
python binary_image_passcode.py encode cover.png --text-file message.txt --output encrypted.png --key friend

# JPG图片正文
python binary_image_passcode.py encode-image cover.png --image-file secret.jpg --output encrypted.png --key friend

# PNG无损图片正文
python binary_image_passcode.py encode-image large_cover.png --image-file secret.png --lossless --output encrypted.png --key friend

# 根据消息实际类型选择输出格式
python binary_image_passcode.py decode encrypted.png --output message.txt --key friend
python binary_image_passcode.py decode encrypted.png --output restored.jpg --key friend
python binary_image_passcode.py decode encrypted.png --output restored.png --key friend
```

`capacity`显示文字/JPG分块布局，不是PNG文件容量查询；PNG容量在实际图片加密时检查。`--strength strong`增强分块冗余，`--force`明确允许覆盖已有输出文件。

## 12. 常见问题与维护

**总像素够大为何仍容量不足？** 分块模式还受长宽比、留白与冗余门槛影响；PNG模式取决于压缩后文件字节数。换用更大、较接近方形的底图，或改用JPG正文。

**密钥一样为何解密失败？** 检查前导零、库内选项，以及收到的是否为未经缩放、编辑、截图或转码的原始PNG。

**刷新后为何列表不变？** 本机密钥未改变时，刷新后的列表相同是正常结果，反馈会显示读取到的数量。

**程序会上传正文或密钥吗？** 消息处理在本机完成，程序不内置远程消息服务器。安装依赖、下载云端照片、云盘文件与系统相册同步，是相应工具或系统服务的行为。

第三方许可随`licenses/`、各平台源码和`THIRD_PARTY_NOTICES.md`提供，再分发时应保留。

跨端兼容开发须保持编码表、端序、随机值长度、派生标签、时间字段、认证附加数据与像素规则一致。改变消息语义时应明确版本化，使用固定向量和跨端往返验证；界面更新不应直接改动协议派生域。
