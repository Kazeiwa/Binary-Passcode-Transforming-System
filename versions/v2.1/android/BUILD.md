# Android build and architecture

This application has no bundled Python runtime, native ABI libraries, network permission or third-party runtime dependencies. The APK supports Android API 26 and later, targets API 36, and uses package ID `org.binarypasscode.image`. Public Android release: 1.0 / versionCode 1.

## Build

Requirements: Python 3, JDK 17+, Android SDK platform 36 and build tools 36.0.0.

```powershell
python build_android.py --sdk C:/Android/Sdk --work C:/build/bip-android --output binary_image_passcode.apk
```

On Linux, use the same command with Linux paths. The script invokes AAPT2, javac, D8, apksigner and zipalign; it does not need an NDK or Gradle. An optional `--aapt2` argument selects a compatible AAPT2 executable.

Set `BIP_SIGNING_STORE` and `BIP_SIGNING_PASSWORD_FILE` to reuse an existing PKCS#12 signing certificate and password file. The alias is `binary_image_passcode`. If absent, the script creates local signing material beside the build directory. Back up both files privately. Never distribute them or change the signing certificate for an application update. The source and user release archives exclude all signing material.

## Modules

| File | Responsibility |
| --- | --- |
| `Crypto.java` | 60,000-unit state codec, 48-byte nonce, encrypted seconds, HKDF/HMAC envelope |
| `Shake.java` | SHAKE256 deterministic slot permutation |
| `Codes.java` | GF(256) matrix erasure code and 32-parity-byte Reed–Solomon correction |
| `Transport.java` | Tile layout, RGB parity slots, three finders, crop and rotation recovery |
| `Images.java` | Android image reading, EXIF orientation, alpha compositing, streaming RGB PNG writer |
| `KeyVault.java` | Android Keystore, encrypted multi-key JSON, atomic storage and password backup |
| `MainActivity.java` | User interface, document pickers and asynchronous cancellable jobs |

The wire format matches the desktop image profile: envelope 37,595 bytes, body 300,000 bits, 48-byte nonce, a 5-byte container for the encrypted seconds value modulo 10,000,000,000. The internal domain/version bytes are protocol identifiers. All three RGB channels carry independent bits. Positions and character codec match the Python implementation exactly.

Every authenticated tile holds a 66-byte packet header, RS protection, an erasure shard and a truncated 128-bit packet HMAC. The complete envelope has a 256-bit HMAC. Authentication precedes releasing plaintext. Any k valid shards recover the envelope; finder placement and tile decoding do not depend on original image dimensions.

The device vault encrypts the complete record with AES-256-GCM and a non-exportable Android Keystore key. Portable Android backups use a separate password-derived AES-256-GCM key, PBKDF2-HMAC-SHA256 (210,000 iterations), 16-byte salt, 12-byte IV, and authenticated header `BIPAK1`. The backup format is deliberately separate from desktop vault storage. The portable 128-digit communication key is shared across platforms.

The activity uses system document pickers instead of broad storage access, prevents automatic app-data backup and screenshots, and does not save plaintext messages. Temporary encrypted images are deleted on cancellation, saving or destruction. Memory checks never silently downsample an encrypted image.

## Tests

`tests/CoreTest.java` runs on a desktop JDK and tests the protocol without Android dependencies. It also encodes/decodes PNG fixtures through Java ImageIO for desktop interoperability testing. `tests/PngTest.java` exercises the actual APK streaming PNG writer (add Android's `android.jar` to the classpath). `tests/AndroidUiTest.java` runs with Robolectric 4.16.1; see `tests/run_ui_tests.py`.

```powershell
mkdir work
javac -encoding UTF-8 -d work/classes src/org/binarypasscode/image/Crypto.java src/org/binarypasscode/image/Shake.java src/org/binarypasscode/image/Codes.java src/org/binarypasscode/image/Transport.java tests/CoreTest.java
java -cp work/classes org.binarypasscode.image.CoreTest
python tests/run_ui_tests.py --maven mvn
```

The Robolectric suite uses a clearly isolated **test-only in-memory AndroidKeyStore provider**. It tests vault data flows, AES-GCM records, backup authentication, dialogs, file access and native rendering; it cannot establish physical-device hardware-backed keystore behavior. No test key or test provider is compiled into the APK.

Reference specifications: [FIPS 202 / SHAKE256](https://csrc.nist.gov/pubs/fips/202/final), [Android Storage Access Framework](https://developer.android.com/training/data-storage/shared/documents-files), [Robolectric testing](https://robolectric.org/getting-started/).
