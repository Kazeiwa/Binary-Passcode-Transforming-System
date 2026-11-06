# 安卓V2.6测试报告

日期：2026-11-04。宿主Windows、JDK 17、Android SDK 36。测试使用生成图片、临时密钥库和公开演示数据，不读取用户真实通信密钥。

## 协议与Windows互通

18项互通用例通过：

- Windows/Python JPG到Java，均衡与增强两种冗余。
- 两种JPG配置的裁剪、旋转恢复。
- Java JPG载体到Windows/Python，以及固定秒数图片信封读取。
- Windows/Python PNG到Java，RGBA像素与alpha精确恢复。
- Java PNG载体到Windows/Python，RGBA精确恢复。
- PNG三种非零直角方向恢复。
- 错误密钥拒绝且不产生图片文件。
- 正文比特损坏拒绝且不产生图片文件。
- 已有V2.1文字图片读取。
- 1080P高噪声RGB PNG、4800×4800底图，Windows到Java及Java到Windows双向恢复。

另有纯Java核心测试通过：SHAKE已知向量、完整BMP非代理码点、60,000单元、时间终点、消息认证、RS每码字16字节纠错及GF(256)外层恢复。APK使用的PngWriter经独立ImageIO读取，随机RGBA逐像素相同。

高容量大图测试在桌面JVM运行，不能据此推断每台手机都能处理同样尺寸。PNG写入采用Sub过滤和Deflate级别6，避免高重复低位模式在级别9下过长的压缩耗时。

## 安卓框架流程

Robolectric 4.16.1，8项测试全部通过。基础流程含Android 9框架，新增图片流程与原生绘图使用Android 15框架。

保留：启动与三页导航、字符/单元计数、密钥CRUD、默认选择、记录重新读取、备份合并及认证、坏备份拒绝、输入校验、取消、系统文档读取、AtomicFile恢复和损坏库恢复入口。

新增：

- 原生BitmapFactory不预乘alpha读取随机RGBA，逐像素一致；包含透明像素中的RGB值。
- PNG预处理和输出后重新读取，RGBA一致；空间不足时提示、不继续缩小。
- 系统文件提供者选择秘密图片和底图。
- 图片模式与PNG选择、裁剪选项状态、文字切回。
- 真正调用图片加密、导出载体PNG、选择载体、解密、预览、保存PNG/JPG。
- 保存字节与已认证图片完全相同；PNG逐像素及alpha相同。
- 底图/密图双预览、图片结果时复制文字控件隐藏、保存格式切换。
- 清空结果移除密图并保留底图；生成时间显示到秒，无原始时间戳。
- 原生绘图截图生成并检查，页面内容可滚动，双预览并排。

测试的AndroidKeyStore是明确隔离的内存提供者，用于验证流程和AES-GCM记录，不等同于硬件密钥库实测。测试类与提供者不进入APK。

## 发布检查

包名org.binarypasscode.image，versionCode 26，versionName 2.6，minSdk 26、targetSdk 36、debuggable=false。使用原安卓图片终端的发布证书，满足同包名、同签名、高版本号的升级条件。

APK签名v2/v3验证、ZIP对齐与完整性检查通过；无联网或全盘存储权限，无Python或原生ABI库，无测试类、测试私钥或签名私钥。用户包、源码包及APK提供SHA-256。

未连接安卓真机，未验证厂商文件选择器、真实硬件Keystore、Android 8或Android 16真机运行。API 36已编译验证，未在该API框架运行GUI测试。截图来自测试框架原生绘图，不是真机截图。
