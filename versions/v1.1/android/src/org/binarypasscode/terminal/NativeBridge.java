package org.binarypasscode.terminal;

import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** Platform cryptography provider for the shared C++ protocol core. */
public final class NativeBridge {
    static { System.loadLibrary("binary_passcode_terminal"); }
    private static final SecureRandom RANDOM = new SecureRandom();
    private NativeBridge() {}
    public static native String encrypt(String text, String key);
    public static native String[] decrypt(String cipher, String key);
    public static native String generateKey();
    public static byte[] randomBytes(int size) {
        if (size < 0 || size > 4096) throw new IllegalArgumentException("随机数长度无效。");
        byte[] result = new byte[size];
        RANDOM.nextBytes(result);
        return result;
    }
    public static byte[] hmacSha256(byte[] key, byte[] data) throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(data);
    }
}
