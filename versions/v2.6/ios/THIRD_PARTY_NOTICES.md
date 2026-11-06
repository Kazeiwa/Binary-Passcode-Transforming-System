# Third-party components

The iOS app uses the stb_image 2.30 and stb_image_write 1.16 headers from the official nothings/stb repository, pinned to commit `f0569113c93ad095470c54bf34a17b36646bbbb5`.

Source: https://github.com/nothings/stb/tree/f0569113c93ad095470c54bf34a17b36646bbbb5

Each vendored header includes its complete dual MIT / public-domain license. Those notices are retained unchanged in `Vendor/`. The files are used under the MIT option.

SHA-256:

```text
cbd5f0ad7a9cf4468affb36354a1d2338034f2c12473cf1a8e32053cb6914a05  stb_image.h
594c2fe35d49488b4382dbfaec8f98366defca819d916ac95becf3e75f4200b3  stb_image_write.h
```

Apple Foundation, UIKit, SwiftUI, Security, ImageIO, CommonCrypto and CryptoKit are supplied by the operating system and Xcode SDK, and are not redistributed in the source archive.

The Windows CNG backend in `Tests/WindowsCrypto.cpp` is only used for host-side verification. It is not part of the iOS application target. Likewise, Python/Pillow/NumPy/cryptography/reedsolo and local syntax parsers are verification tools, not app dependencies.
