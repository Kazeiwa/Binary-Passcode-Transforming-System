package org.binarypasscode.terminal;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Wraps the portable 128-digit communication key using a device-local AES key. */
final class KeyStorage {
    private static final String ALIAS = "binary_passcode_terminal.storage.v1";
    private final SharedPreferences preferences;
    KeyStorage(Context context) {
        preferences = context.getSharedPreferences("binary_passcode_terminal", Context.MODE_PRIVATE);
    }
    static void validate(String key) {
        if (key == null || !key.matches("[0-9]{128}"))
            throw new IllegalArgumentException("密钥必须是恰好128位的半角数字，前导零必须保留。");
    }
    private SecretKey wrappingKey(boolean create) throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(ALIAS)) return (SecretKey) store.getKey(ALIAS, null);
        if (!create) throw new IllegalStateException("本机密钥保护信息已丢失，请重新导入原始密钥。");
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true).build());
        return generator.generateKey();
    }
    String load() throws Exception {
        String stored = preferences.getString("cipher", null);
        String iv = preferences.getString("iv", null);
        if (stored == null && iv == null) return null;
        if (stored == null || iv == null) throw new IllegalStateException("本地密钥记录不完整，请重新导入原始密钥。");
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, wrappingKey(false), new GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)));
            String key = new String(cipher.doFinal(Base64.decode(stored, Base64.NO_WRAP)), StandardCharsets.US_ASCII);
            validate(key);
            return key;
        } catch (Exception error) {
            throw new IllegalStateException("本地密钥无法读取，请重新导入原始128位密钥。", error);
        }
    }
    String require() throws Exception {
        String key = load();
        if (key == null) throw new IllegalStateException("尚未配置密钥，请先进入密钥管理导入或生成。");
        return key;
    }
    void save(String key) throws Exception {
        validate(key);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, wrappingKey(true));
        byte[] encrypted = cipher.doFinal(key.getBytes(StandardCharsets.US_ASCII));
        boolean saved = preferences.edit()
                .putString("iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP))
                .putString("cipher", Base64.encodeToString(encrypted, Base64.NO_WRAP)).commit();
        if (!saved) throw new IllegalStateException("密钥保存失败，请检查设备存储空间。");
    }
}
