# 二进制密码转换终端 V1.1 — C++版

Windows 10/11 x64 双击 `binary_passcode_terminal.exe`，不需要安装 Python，也不需要另外附带 C++ 运行库 DLL。菜单为：1 加密、2 解密、3 密钥管理、0 退出；每次操作后返回菜单。

先在密钥管理中导入已有的128位十进制私钥，或生成新私钥。前导零必须保留。导入与更新使用同一个菜单项；显示密钥需要主动选择菜单4。

本C++版与最新版 `binary_passcode_terminal.py` 使用相同的加密时间区和正文格式，可互相加解密，本地密钥也兼容。密文固定200位半角数字，生成时间采用北京时间、精确到分钟，原点为2000-01-01 00:00，最后可用时间为2190-02-17 10:39；超出范围会报错。短正文以空格补足100个编码单元。正文最多100字符，编码后也不能超过100单元；大小写切换、数字开闭也占单元。现支持BMP全部Unicode标量值，已有基础字符继续使用短编码，其余BMP字符各占6单元；代理码点及补充平面字符不支持。全角标点和 `@#$^&’` 等符号已支持。交互输入仍按单行读取，控制字符的录入和显示取决于终端。

## 本地密钥

- Windows：使用当前用户的 DPAPI 加密保存到程序旁的 `binary_passcode_terminal.key`，与 Python 版兼容。程序应放在允许写入的文件夹。受保护文件无法直接搬到其他电脑或账户使用，需在目标机器导入原始128位私钥。
- Linux：使用系统密钥环 Secret Service，通过 `secret-tool` 保存和读取，不写入明文密钥文件。通常登录桌面并解锁登录密钥环后便无需每次输密码；是否自动解锁由桌面密钥环配置决定。

Linux 需要安装 `secret-tool`（Debian/Ubuntu 对应包名为 `libsecret-tools`）、运行中的 Secret Service（例如 GNOME Keyring 或提供该接口的 KWallet）和 OpenSSL 运行库 `libcrypto.so.3` 或 `libcrypto.so.1.1`。纯命令行、SSH、没有会话总线或密钥环未解锁的环境可能无法读写本地密钥，程序会中文报错。

## Linux 编译

需要支持 C++17 的编译器：

```sh
g++ -std=c++17 -O2 binary_passcode_terminal.cpp -ldl -o binary_passcode_terminal
./binary_passcode_terminal
```

也可以使用 CMake：

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```

Windows 的 EXE 不能直接作为 Linux 原生程序运行，Linux 需使用上述源码编译。当前交付的 Linux 分支未在真实 Linux 桌面密钥环中运行验证。

## Android编译

`binary_passcode_terminal.cpp` 已增加 `__ANDROID__` 分支和JNI入口，复用桌面编码、时间和正文封装。Android平台通过Java安全提供程序执行HMAC-SHA256及SecureRandom；不依赖手机上的外部OpenSSL文件。界面和本地密钥存储代码在 `android/src`。

使用JDK 17或以上，安装Android SDK的 `platforms;android-36`、`build-tools;36.0.0` 和 `ndk;30.0.16248370`，然后运行：

```sh
python android/build_android.py --sdk /path/to/android-sdk --work /path/to/build-directory
```

输出为 `binary_passcode_terminal.apk`，包含arm64-v8a、armeabi-v7a和x86_64，最低Android 8.0/API 26。APK内静态链接C++运行库，库及ZIP布局兼容16KB页对齐。该脚本执行正式签名和校验，应用未启用debuggable。

首次构建会在构建目录旁的 `android-signing` 目录生成APK签名证书 `release.p12` 和密码文件。两者用于后续版本的覆盖升级，务必备份；这与聊天通信的128位密钥是两套不同的用途。也可通过 `BPT_SIGNING_STORE` 和 `BPT_SIGNING_PASSWORD_FILE` 指定已有签名资料。签名资料、通信密钥及SDK均不包含在源码发布包中。

本次构建主机的原生资源工具在写ZIP目录时退出异常，脚本只在确认所有预期资源条目齐全、长度与CRC全部匹配后重建ZIP目录；如有缺失或校验失败则停止。最终APK另经官方apksigner与zipalign独立检查。

## 已完成验证

Windows 实际运行通过240组编码、解码和固定随机编号下的密文一致性对照，共1258次 EXE 调用；还穷举全部63488个BMP标量值，对照Python/C++编码并检查还原，确认87个基础字符使用短编码、其余63401个字符使用6单元转义。测试包含原点、范围终点、闰日、加密时间区全零、非法长度、时间、校验码及字段越界，并验证了Python与C++的DPAPI密钥文件互读、旧明文密钥自动迁移和菜单连续操作。所有密钥测试均使用临时目录中的专用测试密钥。

## 格式说明

密文结构及加密算法与 Python 版一致：8位加密分钟序号、39位随机编号、151位加密正文、2位校验码。解密时先利用私钥和随机编号还原时间，再恢复正文。校验码用于检查输入损坏，不构成密码学认证；错误私钥不保证都能被识别。末尾补齐空格会保留在解密结果中。旧版明文日期格式密文请使用 `decimal_cipher_200_v2_legacy.py` 读取。

源码中的 `--test-io` 是用于与 Python 版进行一致性验证的标准输入接口，正常双击使用不需要它。
