# Binary Passcode Transforming System

二进制密码转换终端：支持文字编码、加密解密，以及将文字或图片加密嵌入 PNG 图像。

## V2.6 图片版

- 支持 Windows、Linux、Android、iOS / iPadOS。
- 支持文字、JPG 压缩图片和 PNG 无损图片消息，保留秒级时间信息。
- 提供多密钥管理、密钥备份与恢复、消息完整性验证。
- 安卓与 iOS 支持从相册或文件选择图片，保存到相册或文件。
- 所有消息处理在本机完成，载体图片以 PNG 文件或原图传递。

## 源码与文档

| 版本 | 平台与说明 |
| --- | --- |
| V1.1 数字终端 | [Python、C++、Android](versions/v1.1/) |
| V2.1 图片版 | [Windows / Linux](versions/v2.1/desktop/) · [Android](versions/v2.1/android/) |
| V2.6 图片版 | [Windows / Linux](versions/v2.6/desktop/) · [Android](versions/v2.6/android/) · [iOS](versions/v2.6/ios/) |

## 运行与构建

- **Windows / Linux**：进入 `versions/v2.6/desktop`，运行 `run_windows.bat` 或 `bash run_linux.sh`。详见 [使用与开发说明](versions/v2.6/desktop/README.md)。
- **Android**：准备 JDK 和 Android SDK，按照 [构建说明](versions/v2.6/android/BUILD.md) 编译 APK。
- **iOS**：使用 macOS / Xcode，或在 GitHub Actions 手动运行 **Build iOS V2.6**，下载构建产物并自行签名安装。详见 [iOS 说明](versions/v2.6/ios/README.md)。
