# Android V2.6 build and implementation

Pure Java Android application, minimum API 26, target API 36, package `org.binarypasscode.image`, versionCode 26/versionName 2.6. No Python runtime or native ABI libraries are bundled.

## Build

Requires Python 3, JDK 17+, Android platform 36 and build-tools 36.0.0:

```powershell
python build_android.py --sdk C:/Android/Sdk --work C:/build/bip26-android --output binary_image_passcode_v2.6.apk
```

The script runs AAPT2, javac, D8, zipalign and apksigner. It removes old generated class files before compilation so host test classes cannot enter the APK. `--aapt2` can select a compatible executable.

Signing: `BIP_SIGNING_STORE` and `BIP_SIGNING_PASSWORD_FILE` select the private PKCS#12 store and password file; alias `binary_image_passcode`. Defaults keep signing files beside the build directory, outside the source tree. Preserve the existing certificate to allow in-place upgrades and access to the existing Android Keystore-protected vault. Never include signing material in release archives.

## Modules

| File | Responsibility |
| --- | --- |
| Crypto.java | Five-bit text codec, text envelope and shared utilities |
| ImagePayload.java | JPEG/PNG AEAD, authenticated metadata, time and HKDF |
| Transport.java | Existing tiled RGB parity, variable JPEG envelope, RS and erasure recovery |
| DenseTransport.java | Windows V2.6 full-file PNG transport, authenticated repeated header, affine slots |
| Codes.java / Shake.java | GF(256), RS and deterministic SHAKE slot sorting |
| PngWriter.java | Streaming RGB/RGBA PNG, Sub row filtering and Deflate level 6 |
| Images.java | Carrier bounds, memory checks, reading and streaming output |
| SecretImages.java | Secret-image sampling, EXIF orientation, 1080P adaptation, JPG compression and PNG pixels |
| KeyVault.java | Android Keystore AES-GCM vault and password backup |
| MainActivity.java | UI, dual previews, document pickers and cancellable jobs |

Wire formats, HKDF labels, time offsets, indices and AEAD AAD match the Windows implementation. Text uses the existing BIP2 envelope; image messages use BIP3, kind 1=JPEG / 2=PNG. JPEG travels in authenticated BIPT tiles; PNG uses the BIPD dense header and complete-file payload. Public nonces are 48 bytes. Integers are big-endian, bits MSB-first. SHAKE ordering compares unsigned uint64 values; dense positions use unsigned remainder on the seed words.

Dense PNG reserves a fixed 4% border and 2208 header bits, authenticates three 92-byte header copies, and scatters the AEAD bytes using the exact Windows coprime affine sequence. It does not promise crop recovery or body error correction. Rotation tries four right-angle orientations.

Secret PNG input is decoded with `inPremultiplied=false`. When no resize is needed, raw unassociated RGBA samples are written by PngWriter instead of round-tripping through a premultiplied Canvas, preserving even hidden RGB values at alpha=0. Resizing occurs before the lossless guarantee; normalized values are 8-bit RGB/RGBA. Preview bitmaps may be premultiplied for display without changing the authenticated PNG bytes.

JPG uses the Android JPEG encoder, quality candidates 85 to 50 by steps of 5; if necessary, dimensions reduce by 15% and quality candidates repeat. Encoded bytes need not match Pillow's JPEG encoder, but the file is authenticated and interoperable. PNG bytes likewise need not match Pillow's compressor; decoded pixels do.

Carrier reading never downsamples an encrypted file. It checks the Java heap before allocating bitmap/pixel buffers; large carriers may exceed a particular phone's heap despite being below the 80MP format bound. Secret images use sampled decoding and a 1080P aspect-preserving target; supported source formats depend on Android codecs. TIFF is not claimed as supported by the built-in decoder.

## Key storage

The package ID, Keystore alias, encrypted JSON file and BIPAK1 backup format are unchanged. The full multi-key record is AES-256-GCM encrypted with a non-exportable device key. Backups use PBKDF2-HMAC-SHA256 (210000 rounds), 16-byte salt and AES-GCM. Raw 128-digit communication keys are portable; Android and Windows vault backup formats are separate.

## Tests

`tests/CoreTest.java` exercises text, full BMP, RS and GF primitives on a JDK. `tests/ImageCoreTest.java` is an ImageIO-based host interoperability harness; it is never compiled into the APK. `tests/AndroidUiTest.java` uses Robolectric 4.16.1; run:

```powershell
python tests/run_ui_tests.py --maven mvn
```

The runner downloads development dependencies into its cache. Native graphics tests use the Android 15 framework; other flows include Android 9. The test-only AndroidKeyStore provider is in-memory and cannot demonstrate hardware-backed Keystore behavior. Production uses the real OS provider. See TEST_REPORT.md for verified scope and physical-device limitations.
