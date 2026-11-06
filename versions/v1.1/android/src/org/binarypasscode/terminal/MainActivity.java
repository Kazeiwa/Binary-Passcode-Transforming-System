package org.binarypasscode.terminal;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.PersistableBundle;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int INK = Color.rgb(24, 38, 53), MUTED = Color.rgb(93, 108, 124), ACCENT = Color.rgb(14, 112, 101);
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private KeyStorage storage;
    private LinearLayout content;
    private final View[] panels = new View[3];
    private final Button[] tabs = new Button[3];
    private TextView keyStatus;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        storage = new KeyStorage(this);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        LinearLayout root = column();
        root.setBackgroundColor(Color.rgb(243, 246, 248));
        root.setPadding(dp(20), dp(18), dp(20), dp(12));
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            v.setPadding(dp(20) + insets.getSystemWindowInsetLeft(), dp(18) + insets.getSystemWindowInsetTop(),
                    dp(20) + insets.getSystemWindowInsetRight(), dp(12) + insets.getSystemWindowInsetBottom());
            return insets;
        });
        TextView title = text("二进制密码转换终端", 23, INK);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        root.addView(title);
        TextView subtitle = text("V1.1  ·  本地处理", 13, MUTED);
        subtitle.setPadding(0, dp(6), 0, dp(20));
        root.addView(subtitle);
        LinearLayout navigation = new LinearLayout(this);
        String[] names = {"加密", "解密", "密钥"};
        for (int i = 0; i < 3; i++) {
            final int index = i;
            tabs[i] = button(names[i]);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, dp(46), 1);
            if (i != 2) lp.rightMargin = dp(8);
            navigation.addView(tabs[i], lp);
            tabs[i].setOnClickListener(v -> select(index));
        }
        root.addView(navigation);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        content = column();
        content.setPadding(0, dp(20), 0, dp(20));
        scroll.addView(content);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        panels[0] = cryptoPanel(false);
        panels[1] = cryptoPanel(true);
        panels[2] = keyPanel();
        setContentView(root);
        root.requestApplyInsets();
        select(0);
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private LinearLayout column() {
        LinearLayout view = new LinearLayout(this);
        view.setOrientation(LinearLayout.VERTICAL);
        return view;
    }
    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setLineSpacing(dp(3), 1);
        return view;
    }
    private GradientDrawable background(int color) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color); drawable.setCornerRadius(dp(12));
        return drawable;
    }
    private Button button(String label) {
        Button view = new Button(this);
        view.setText(label); view.setAllCaps(false); view.setTextSize(15);
        view.setTextColor(ACCENT); view.setBackground(background(Color.WHITE));
        view.setMinHeight(0); view.setMinimumHeight(0);
        return view;
    }
    private void addButton(LinearLayout parent, Button button) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, dp(48));
        lp.topMargin = dp(12); parent.addView(button, lp);
    }
    private EditText editor(String hint) {
        EditText view = new EditText(this);
        view.setHint(hint); view.setTextColor(INK); view.setHintTextColor(MUTED); view.setTextSize(16);
        view.setGravity(Gravity.TOP | Gravity.START); view.setPadding(dp(14), dp(14), dp(14), dp(14));
        view.setBackground(background(Color.WHITE)); view.setMinLines(4);
        view.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        view.setImeOptions(EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING);
        view.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        view.setSaveEnabled(false);
        return view;
    }
    private void select(int index) {
        content.removeAllViews(); content.addView(panels[index]);
        for (int i = 0; i < 3; i++) {
            tabs[i].setBackground(background(i == index ? ACCENT : Color.WHITE));
            tabs[i].setTextColor(i == index ? Color.WHITE : ACCENT);
        }
        if (index == 2) refreshKeyStatus();
    }
    private View cryptoPanel(boolean decrypting) {
        LinearLayout panel = column();
        panel.addView(text(decrypting ? "还原正文" : "生成密文", 20, INK));
        TextView help = text(decrypting ? "输入完整的200位半角数字，使用本机已保存的密钥解密。"
                : "支持BMP范围内的文字和符号。最多100字符、100编码单元；基础字符以外的字符各占6单元，混合输入还会占用额外容量。", 13, MUTED);
        help.setPadding(0, dp(8), 0, dp(14)); panel.addView(help);
        EditText input = editor(decrypting ? "在此粘贴200位密文" : "在此输入正文");
        if (decrypting) input.setTypeface(Typeface.MONOSPACE);
        panel.addView(input, new LinearLayout.LayoutParams(-1, -2));
        TextView count = text(decrypting ? "0 / 200 位" : "0 / 100 字符", 12, MUTED);
        count.setPadding(0, dp(6), 0, 0); panel.addView(count);
        input.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            public void onTextChanged(CharSequence s, int start, int before, int added) {
                int length = Character.codePointCount(s, 0, s.length());
                count.setText(length + (decrypting ? " / 200 位" : " / 100 字符"));
            }
            public void afterTextChanged(Editable e) {}
        });
        Button action = button(decrypting ? "解密" : "加密");
        action.setBackground(background(ACCENT)); action.setTextColor(Color.WHITE); addButton(panel, action);
        TextView timestamp = text("", 13, MUTED);
        timestamp.setPadding(0, dp(18), 0, dp(8)); panel.addView(timestamp);
        TextView result = text("结果将在这里显示", 16, MUTED);
        result.setTextIsSelectable(true); result.setPadding(dp(14), dp(14), dp(14), dp(14));
        result.setBackground(background(Color.WHITE)); result.setMinHeight(dp(100));
        if (!decrypting) result.setTypeface(Typeface.MONOSPACE);
        panel.addView(result, new LinearLayout.LayoutParams(-1, -2));
        final String[] currentResult = {null};
        Button copy = button(decrypting ? "复制正文" : "复制密文"); addButton(panel, copy);
        copy.setOnClickListener(v -> {
            if (currentResult[0] == null) toast("请先完成转换。");
            else copy(currentResult[0]);
        });
        action.setOnClickListener(v -> {
            String value = input.getText().toString();
            currentResult[0] = null; timestamp.setText(""); result.setText("正在处理…"); action.setEnabled(false);
            executor.execute(() -> {
                try {
                    String key = storage.require();
                    String[] response = decrypting ? NativeBridge.decrypt(value, key) : new String[] {"", NativeBridge.encrypt(value, key)};
                    runOnUiThread(() -> {
                        if (isDestroyed()) return;
                        currentResult[0] = response[1]; result.setTextColor(INK); result.setText(response[1]);
                        timestamp.setText(decrypting ? "生成时间（北京时间）：" + response[0] : "加密结果 · 200位数字");
                        action.setEnabled(true);
                    });
                } catch (Exception | LinkageError error) {
                    runOnUiThread(() -> {
                        if (isDestroyed()) return;
                        result.setTextColor(Color.rgb(169, 50, 47)); result.setText("错误：" + message(error)); action.setEnabled(true);
                    });
                }
            });
        });
        return panel;
    }
    private View keyPanel() {
        LinearLayout panel = column();
        panel.addView(text("密钥管理", 20, INK));
        TextView info = text("导入双方约定的128位数字密钥，前导零必须保留。密钥由本机系统加密保存；需要传递时可主动显示或复制。", 14, MUTED);
        info.setPadding(0, dp(10), 0, dp(16)); panel.addView(info);
        keyStatus = text("", 15, ACCENT); panel.addView(keyStatus);
        Button importKey = button("导入或更新密钥"); addButton(panel, importKey);
        importKey.setOnClickListener(v -> importKey());
        Button generate = button("生成并保存新密钥"); addButton(panel, generate);
        generate.setOnClickListener(v -> new AlertDialog.Builder(this).setTitle("生成新密钥")
                .setMessage("新密钥将替换当前密钥。需要读取旧消息时，请先显示并备份旧密钥。")
                .setNegativeButton("取消", null).setPositiveButton("生成", (d, which) -> {
                    try { storage.save(NativeBridge.generateKey()); refreshKeyStatus(); toast("新密钥已生成并保存。"); }
                    catch (Exception | LinkageError error) { showError(error); }
                }).show());
        Button show = button("显示当前密钥"); addButton(panel, show);
        show.setOnClickListener(v -> {
            try {
                String key = storage.require();
                TextView value = text(key, 16, INK); value.setTypeface(Typeface.MONOSPACE); value.setTextIsSelectable(true);
                value.setPadding(dp(24), dp(16), dp(24), dp(16));
                AlertDialog dialog = new AlertDialog.Builder(this).setTitle("当前密钥").setView(value)
                        .setNegativeButton("关闭", null).setPositiveButton("复制密钥", (d, which) -> copy(key)).create();
                dialog.getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE); dialog.show();
            } catch (Exception error) { showError(error); }
        });
        TextView note = text("卸载或清除应用数据前，请备份原始密钥。手机上的加密存储记录不能直接搬到另一台设备使用。", 13, MUTED);
        note.setPadding(0, dp(20), 0, 0); panel.addView(note);
        return panel;
    }
    private void refreshKeyStatus() {
        try { keyStatus.setText(storage.load() == null ? "尚未配置密钥" : "已配置密钥 · 本机加密保护"); }
        catch (Exception error) { keyStatus.setText("密钥需要重新导入"); }
    }
    private void importKey() {
        EditText value = editor("128位半角数字密钥"); value.setMinLines(2); value.setTypeface(Typeface.MONOSPACE);
        value.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("导入或更新密钥").setView(value)
                .setNegativeButton("取消", null).setPositiveButton("保存", null).create();
        dialog.getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            try { storage.save(value.getText().toString()); value.setText(""); refreshKeyStatus(); toast("密钥已保存。"); dialog.dismiss(); }
            catch (Exception error) { value.setError(message(error)); }
        }));
        dialog.show();
    }
    private void copy(String value) {
        ClipData data = ClipData.newPlainText("转换结果", value);
        PersistableBundle extras = new PersistableBundle();
        extras.putBoolean("android.content.extra.IS_SENSITIVE", true); data.getDescription().setExtras(extras);
        ((ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE)).setPrimaryClip(data);
        toast("已复制。");
    }
    private String message(Throwable error) {
        return error.getMessage() == null ? "操作未完成，请重试。" : error.getMessage();
    }
    private void showError(Throwable error) { new AlertDialog.Builder(this).setTitle("操作未完成").setMessage(message(error)).setPositiveButton("确定", null).show(); }
    private void toast(String message) { Toast.makeText(this, message, Toast.LENGTH_SHORT).show(); }
    @Override protected void onDestroy() { executor.shutdown(); super.onDestroy(); }
}
