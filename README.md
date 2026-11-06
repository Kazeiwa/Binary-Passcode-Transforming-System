# Binary Passcode Transforming System

二进制密码转换终端的历代源码合集，包含目前本地保存的 **V1.0、V1.1、V2.1、V2.5、V2.6**。

最新版：[V2.6 使用与开发说明](versions/v2.6/desktop/README.md)。图片版支持 Windows、Linux、Android 和 iOS / iPadOS。

## 源码导航

| 版本 | 源码与文档 |
| --- | --- |
| V1.0 | [Python 终端](versions/v1.0/)，并保留本地另存的 `binary_passcode_terminalV1.0` 快照 |
| V1.1 | [Python、C++ 与 Android](versions/v1.1/) |
| V2.1 | [Windows / Linux](versions/v2.1/desktop/) · [Android](versions/v2.1/android/) |
| V2.5 | [Windows / Linux](versions/v2.5/desktop/) |
| V2.6 | [Windows / Linux](versions/v2.6/desktop/) · [Android](versions/v2.6/android/) · [iOS](versions/v2.6/ios/) |

未收集到的早期平台版本不以新版冒充。历史目录保留各自的说明、依赖、构建脚本、测试与第三方许可；协议兼容性和运行要求请查看对应版本文档。

V1.1 的源码包快照与散装源码如有不同，打包时的对应文件保留在 `packaged_snapshot`，主目录采用本地散装文件。V1.0 的两份本地源码均保留。`SOURCE_MANIFEST.json` 记录来源与校验值。

## 最新版运行与构建

- 桌面端：进入 `versions/v2.6/desktop`，Windows 使用 `run_windows.bat`，Linux 使用 `bash run_linux.sh`。依赖与打包说明见该目录 README。
- Android：进入 `versions/v2.6/android`，按照 [构建说明](versions/v2.6/android/BUILD.md) 准备 JDK 与 Android SDK，再运行构建脚本。
- iOS：进入 `versions/v2.6/ios`，使用 macOS / Xcode，或在 GitHub Actions 中手动运行 **Build iOS V2.6**。成功后下载 unsigned IPA；安装需要自行签名，构建细节见 [iOS README](versions/v2.6/ios/README.md)。

V2.6 Android 源码已包含相册 / 文件双入口、相册保存与文件导出、键盘收起，以及加密与解密预览独立状态。

## 仓库内容与安全边界

仓库收录源代码、构建资源、文档、测试和第三方许可，不包含 EXE、APK、IPA、依赖缓存、签名证书或本地通信密钥。测试与示例中的公开测试密钥仅供演示，不应用于实际通信。

保留各版本所附第三方许可；本次整理没有替作者新增开源授权。原始五位编码、加密认证和图像隐写承担不同职责，编码与隐写本身不等于安全加密；各版本的安全能力不同。
