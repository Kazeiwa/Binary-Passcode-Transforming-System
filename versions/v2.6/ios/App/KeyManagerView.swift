import SwiftUI
import UniformTypeIdentifiers
import UIKit

struct KeyManagerView: View {
    private enum InputField: Hashable { case name, key, password }
    @EnvironmentObject private var vault: KeyVault
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var value = ""
    @State private var showValue = false
    @State private var password = ""
    @State private var error: String?
    @State private var deleting: SavedKey?
    @State private var revealed: SavedKey?
    @State private var renaming: SavedKey?
    @State private var newName = ""
    @State private var exporter = false
    @State private var importer = false
    @State private var document: BinaryDocument?
    @State private var working = false
    @State private var savedNotice: String?
    @State private var reloadNotice: String?
    @FocusState private var focusedInput: InputField?
    var body: some View {
        NavigationStack {
            Form {
                Section("已保存的密钥") {
                    if vault.keys.isEmpty { Text("暂无密钥。可生成新密钥，或导入对方提供的128位数字密钥。").foregroundStyle(.secondary) }
                    ForEach(vault.keys) { item in
                        HStack {
                            Button { vault.selected = item.id } label: {
                                HStack { Image(systemName: vault.selected == item.id ? "checkmark.circle.fill" : "circle"); Text(item.name) }
                            }.buttonStyle(.borderless)
                            Spacer()
                            Menu {
                                Button("查看密钥") { revealed = item }
                                Button("重命名") { newName = item.name; renaming = item }
                                Button("删除", role: .destructive) { deleting = item }
                            } label: {
                                Image(systemName: "ellipsis.circle")
                                    .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
                            }
                            .accessibilityLabel("密钥操作")
                            .accessibilityIdentifier("key.actions." + item.name)
                        }
                    }
                    Button("刷新密钥列表", action: reloadKeys)
                        .buttonStyle(.bordered).accessibilityIdentifier("key.reload")
                    if let reloadNotice { Text(reloadNotice).font(.caption).foregroundStyle(.teal).accessibilityIdentifier("key.reloaded") }
                }
                Section("添加密钥") {
                    TextField("密钥名称（不超过80字）", text: $name).textInputAutocapitalization(.never).autocorrectionDisabled().focused($focusedInput, equals: .name).accessibilityIdentifier("key.name")
                    Group {
                        if showValue { TextField("128位半角数字", text: $value).focused($focusedInput, equals: .key) }
                        else { SecureField("128位半角数字", text: $value).focused($focusedInput, equals: .key) }
                    }.keyboardType(.asciiCapableNumberPad).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .accessibilityIdentifier("key.value")
                    Toggle("显示输入的密钥", isOn: $showValue)
                    Text("已输入 \(value.count) / 128 位").font(.caption).foregroundStyle(.secondary)
                    Button("随机生成") {
                        savedNotice = nil
                        value = BIPService.generateKey()
                        if name.isEmpty { name = "密钥 \(vault.keys.count + 1)" }
                    }.buttonStyle(.bordered).accessibilityIdentifier("key.generate")
                    Button("保存并选用", action: saveEnteredKey)
                        .buttonStyle(.borderedProminent).accessibilityIdentifier("key.save")
                    if let savedNotice { Text(savedNotice).font(.caption).foregroundStyle(.teal).accessibilityIdentifier("key.saved") }
                }
                Section("加密备份") {
                    SecureField("备份密码（至少10个字符）", text: $password).textInputAutocapitalization(.never).autocorrectionDisabled().focused($focusedInput, equals: .password)
                    Button("导出密钥备份") {
                        guard !working else { return }; working = true
                        // PBKDF2 is intentionally expensive. Let the progress state render first.
                        DispatchQueue.main.async {
                            perform { document = BinaryDocument(try vault.export(password: password)); exporter = true }
                            working = false
                        }
                    }
                    Button("导入密钥备份") { importer = true }
                    if working { ProgressView("正在处理备份…") }
                    Text("密钥保存在本机系统钥匙串，不同步至iCloud。备份密码与消息密钥不同，请妥善保管。此备份供iOS版本恢复；跨平台请导入128位数字密钥。").font(.caption).foregroundStyle(.secondary)
                }
            }
            .accessibilityIdentifier("key.form")
            .scrollDismissesKeyboard(.interactively)
            .disabled(working)
            .navigationTitle("密钥管理")
            .safeAreaInset(edge: .bottom) {
                if let error {
                    HStack(alignment: .top) {
                        Image(systemName: "exclamationmark.circle.fill").foregroundStyle(.red)
                        Text(error).font(.callout).accessibilityIdentifier("key.error")
                        Spacer()
                        Button { self.error = nil } label: { Image(systemName: "xmark.circle") }.accessibilityLabel("关闭提示")
                    }.padding().background(.regularMaterial)
                }
            }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { focusedInput = nil; value = ""; password = ""; dismiss() }
                }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("收起键盘") { focusedInput = nil }.accessibilityIdentifier("key.keyboardDone")
                }
            }
            .fileExporter(isPresented: $exporter, document: document, contentType: .data, defaultFilename: "binary_image_passcode_keys.bipkeys") { outcome in
                if case .failure(let error) = outcome { self.error = error.localizedDescription }
                document = nil; password = ""
            }
            .fileImporter(isPresented: $importer, allowedContentTypes: [.data]) { outcome in
                perform { let data = try readSelectedFile(outcome.get(), limit: 2_000_000); try vault.restore(data, password: password); password = "" }
            }
            .alert("删除密钥？", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })) {
                Button("取消", role: .cancel) { deleting = nil }
                Button("删除", role: .destructive) { if let item = deleting { perform { try vault.delete(item.id) } }; deleting = nil }
            } message: { Text("删除后无法解密使用该密钥的历史消息。请确认已另行备份。") }
            .alert("重命名密钥", isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
                TextField("新名称", text: $newName)
                Button("取消", role: .cancel) { renaming = nil }
                Button("保存") { if let item = renaming { perform { try vault.rename(item.id, to: newName) } }; renaming = nil }
            }
            .sheet(item: $revealed) { item in
                NavigationStack {
                    VStack(alignment: .leading, spacing: 20) {
                        Text(item.name).font(.title2)
                        Text(item.value).font(.system(.body, design: .monospaced)).textSelection(.enabled).accessibilityIdentifier("key.revealed")
                        Button("复制密钥") { UIPasteboard.general.setItems([["public.utf8-plain-text": item.value]], options: [.localOnly: true, .expirationDate: Date().addingTimeInterval(60)]) }
                        Text("仅向可信接收者传递密钥；复制的密钥60秒后失效。").font(.caption).foregroundStyle(.secondary)
                    }.padding().toolbar { Button("完成") { revealed = nil } }
                }
            }
        }
    }
    private func reloadKeys() {
        focusedInput = nil
        reloadNotice = nil
        perform {
            try vault.load()
            reloadNotice = "已刷新，共\(vault.keys.count)个密钥。"
        }
    }
    private func saveEnteredKey() {
        // Freeze exactly what is displayed before any form state is reset.
        let enteredName = name
        let enteredValue = value
        focusedInput = nil
        savedNotice = nil
        perform {
            try vault.add(name: enteredName, value: enteredValue)
            name = ""; value = ""; showValue = false
            savedNotice = "已保存并选用“\(enteredName)”"
        }
    }
    private func perform(_ action: () throws -> Void) {
        error = nil
        do { try action() } catch { self.error = error.localizedDescription }
    }
}
