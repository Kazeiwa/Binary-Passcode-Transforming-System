import SwiftUI
import UniformTypeIdentifiers
import UIKit

struct ContentView: View {
    @EnvironmentObject private var vault: KeyVault
    @State private var direction = 0
    @State private var mode = 0
    @State private var lossless = false
    @State private var strong = false
    @State private var text = ""
    @FocusState private var textFocused: Bool
    @State private var encryptionCarrier: Data?
    @State private var decryptionCarrier: Data?
    @State private var secret: Data?
    @State private var encryptionCarrierName = "尚未选择底图"
    @State private var decryptionCarrierName = "尚未选择含密文的PNG"
    @State private var secretName = "尚未选择待加密图片"
    @State private var result: BIPOutput?
    @State private var picker = false
    @State private var photoPicker = false
    @State private var loadingPhoto = false
    @State private var pickingSecret = false
    @State private var keyPanel = false
    @State private var busy = false
    @State private var progress = 0.0
    @State private var status = ""
    @State private var error: String?
    @State private var job: CancellationFlag?
    @State private var exporter = false
    @State private var document: BinaryDocument?
    @State private var exportType: UTType = .png
    @State private var exportName = "binary_image_passcode.png"
    @State private var enlarged: Data?
    @State private var savingPhoto = false
    @State private var photoSaveNotice: String?
    private var carrier: Data? { direction == 0 ? encryptionCarrier : decryptionCarrier }
    private var carrierName: String { direction == 0 ? encryptionCarrierName : decryptionCarrierName }
    private var inputLocked: Bool { busy || loadingPhoto || savingPhoto }
    private var countLabel: String {
        if text.isEmpty { return "0 字符 · 0 编码单元" }
        if let n = try? TextCodec.count(text) { return "\(text.count) 字符 · \(n) / 60,000 编码单元" }
        return "\(text.count) 字符 · 包含不支持的字符或超出容量"
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("将文字或图片藏入PNG，使用同一密钥还原。").foregroundStyle(.secondary)
                    Picker("操作", selection: $direction) { Text("加密").tag(0); Text("解密").tag(1) }.pickerStyle(.segmented)
                        .disabled(inputLocked)
                        .onChange(of: direction) { _ in textFocused = false; result = nil; status = "" }
                    GroupBox {
                        HStack {
                            VStack(alignment: .leading) { Text("当前密钥").font(.caption).foregroundStyle(.secondary); Text(vault.current?.name ?? "请先添加密钥") }
                            Spacer(); Button("管理密钥") { textFocused = false; keyPanel = true }.disabled(inputLocked).accessibilityIdentifier("keyManager.open")
                        }.frame(maxWidth: .infinity)
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        imageSourceMenu(title: direction == 0 ? "选择底图" : "选择含密文的PNG", secret: false, icon: "photo.badge.plus")
                        Text(carrierName).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                        if direction == 0 {
                            Text("均衡模式至少313,600像素，增强模式至少484,416像素；短边至少140。推荐1024×1024及以上，图片模式可能需要更大底图。").font(.caption).foregroundStyle(.secondary)
                        } else {
                            Text("可从相册或文件选择原始PNG。请勿选择经过编辑、截图、缩放或聊天软件压缩的图片。").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if direction == 0 { encryptionInputs }
                    previewRow
                    if busy {
                        ProgressView(value: progress)
                        Text(status).font(.caption).foregroundStyle(.secondary)
                        Button("取消操作", role: .cancel) { job?.cancel(); status = "正在取消…" }
                    } else {
                        Button(action: run) { Label(direction == 0 ? "加密并生成PNG" : "解密消息", systemImage: direction == 0 ? "lock.fill" : "lock.open.fill").frame(maxWidth: .infinity).padding(.vertical, 6) }
                            .buttonStyle(.borderedProminent).disabled(carrier == nil || vault.current == nil || inputLocked)
                    }
                    if let result { resultView(result) }
                    HStack { Button("清除内容") { text = ""; secret = nil; result = nil; status = ""; secretName = "尚未选择待加密图片" }.disabled(inputLocked); Spacer(); Text("V2.6").foregroundStyle(.tertiary) }.font(.caption)
                }.padding().disabled(busy && job == nil)
            }
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("二进制图片密码")
            .toolbar { ToolbarItem(placement: .navigationBarTrailing) { Button { error = "密文始终保存为PNG。文字支持BMP范围字符，扩展字符各占6单元，最多60,000单元。图片自动适配至1920×1080以内；PNG模式保留适配后像素，需要完整文件，不能裁剪。JPG与文字模式可在数据块足够时恢复部分裁剪。密钥仅保存在本机钥匙串，请及时备份。" } label: { Image(systemName: "info.circle") } } }
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    if textFocused {
                        Spacer()
                        Button("收起键盘") { textFocused = false }
                            .accessibilityIdentifier("text.keyboardDone")
                    }
                }
            }
            .sheet(isPresented: $keyPanel) { KeyManagerView() }
            .sheet(isPresented: $photoPicker) {
                PhotoPicker(onStart: { loadingPhoto = true }, onFinish: { outcome in
                    loadingPhoto = false
                    photoPicker = false
                    guard let outcome else { return }
                    do {
                        let photo = try outcome.get()
                        acceptImage(photo.data, name: photo.name)
                    } catch { self.error = error.localizedDescription }
                })
                .interactiveDismissDisabled(loadingPhoto)
                .overlay {
                    if loadingPhoto {
                        ZStack {
                            Color.black.opacity(0.18).ignoresSafeArea()
                            ProgressView("正在读取图片，请稍候…")
                                .padding(24).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
                        }
                    }
                }
            }
            .sheet(isPresented: Binding(get: { enlarged != nil }, set: { if !$0 { enlarged = nil } })) {
                if let data = enlarged, let ui = previewImage(data, maxPixel: 3000) {
                    NavigationStack { ScrollView([.horizontal, .vertical]) { Image(uiImage: ui).resizable().scaledToFit().frame(minWidth: 300, idealWidth: 800, maxWidth: 1200) }.toolbar { Button("完成") { enlarged = nil } } }
                }
            }
            .fileImporter(isPresented: $picker, allowedContentTypes: [.image]) { selection in
                do {
                    let url = try selection.get(), data = try readSelectedFile(url)
                    acceptImage(data, name: url.lastPathComponent)
                } catch { self.error = error.localizedDescription }
            }
            .fileExporter(isPresented: $exporter, document: document, contentType: exportType, defaultFilename: exportName) { outcome in
                if case .failure(let error) = outcome { self.error = error.localizedDescription }
                document = nil
            }
            .alert(error == nil ? "保存成功" : "提示", isPresented: Binding(get: { error != nil || photoSaveNotice != nil }, set: { if !$0 { error = nil; photoSaveNotice = nil } })) {
                Button("确定") { error = nil; photoSaveNotice = nil }
            } message: { Text(error ?? photoSaveNotice ?? "") }
            .task { do { try vault.load() } catch { self.error = error.localizedDescription } }
        }
        // Prevent changing input/result associations while a background operation is running.
        .interactiveDismissDisabled(inputLocked)
    }
    private func imageSourceMenu(title: String, secret: Bool, icon: String) -> some View {
        Menu {
            Button { textFocused = false; pickingSecret = secret; photoPicker = true } label: { Label("从相册选择", systemImage: "photo.on.rectangle") }
            Button { textFocused = false; pickingSecret = secret; picker = true } label: { Label("从文件选择", systemImage: "folder") }
        } label: {
            Label(title, systemImage: icon).frame(maxWidth: .infinity)
        }.buttonStyle(.bordered).disabled(inputLocked)
    }
    private func acceptImage(_ data: Data, name: String) {
        if pickingSecret { secret = data; secretName = name }
        else if direction == 0 { encryptionCarrier = data; encryptionCarrierName = name }
        else { decryptionCarrier = data; decryptionCarrierName = name }
        result = nil
        status = ""
    }
    private var encryptionInputs: some View {
        VStack(alignment: .leading, spacing: 12) {
            Picker("正文类型", selection: $mode) { Text("文字").tag(0); Text("图片").tag(1) }.pickerStyle(.segmented).disabled(inputLocked)
                .onChange(of: mode) { _ in textFocused = false; result = nil }
            if mode == 0 {
                TextEditor(text: $text).focused($textFocused).frame(minHeight: 140).padding(4).background(.quaternary, in: RoundedRectangle(cornerRadius: 8)).disabled(inputLocked)
                Text(countLabel).font(.caption).foregroundStyle(.secondary)
                Text("支持英文、数字、标点与BMP字符；表情及部分罕见字暂不支持。").font(.caption).foregroundStyle(.secondary)
            } else {
                imageSourceMenu(title: "选择待加密图片", secret: true, icon: "photo.on.rectangle")
                Text(secretName).font(.caption).foregroundStyle(.secondary)
                Toggle("PNG无损模式", isOn: $lossless).disabled(inputLocked).onChange(of: lossless) { _ in result = nil }
                Text(lossless ? "保留尺寸适配后的8位RGB/RGBA像素。底图容量不足时报错；密文PNG须完整传输，不能裁剪。" : "自动压缩为JPG，必要时继续缩小正文图片以适应底图容量。").font(.caption).foregroundStyle(.secondary)
            }
            if mode == 0 || !lossless { Toggle("增强裁剪恢复", isOn: $strong).disabled(inputLocked).onChange(of: strong) { _ in result = nil } }
        }
    }
    private var previewRow: some View {
        HStack(alignment: .top, spacing: 12) {
            preview(title: direction == 0 ? "底图 / 密文图" : "密文图", data: result?.carrierPNG ?? carrier)
            if mode == 1 && direction == 0 || result?.secretData != nil {
                preview(title: direction == 0 ? "图片正文" : "已还原图片", data: result?.secretData ?? (direction == 0 ? secret : nil))
            }
        }
    }
    private func preview(title: String, data: Data?) -> some View {
        VStack(alignment: .leading) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            if let data, let ui = previewImage(data) {
                Image(uiImage: ui).resizable().scaledToFit().frame(maxWidth: .infinity, maxHeight: 190).onTapGesture { if !inputLocked { enlarged = data } }
            } else { RoundedRectangle(cornerRadius: 10).fill(.quaternary).frame(height: 130).overlay { Image(systemName: "photo").foregroundStyle(.secondary) } }
        }.frame(maxWidth: .infinity)
    }
    @ViewBuilder private func resultView(_ r: BIPOutput) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("操作完成", systemImage: "checkmark.shield.fill").foregroundStyle(.teal)
            Text("生成时间：" + secondsDate(r.seconds)).font(.caption)
            Text(r.details).font(.caption).foregroundStyle(.secondary)
            if direction == 1 && r.secretData == nil {
                Text(r.text).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading).padding().background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                Button("复制正文") { UIPasteboard.general.string = r.text }
                Button("保存正文") { export(Data(r.text.utf8), type: .plainText, name: "message.txt") }
            }
            if let data = r.carrierPNG {
                albumSaveButton("保存密文PNG到相册", data: data, png: true, filename: "binary_image_passcode.png")
                Button("另存密文PNG为文件") { export(data, type: .png, name: "binary_image_passcode.png") }
                    .buttonStyle(.bordered).disabled(inputLocked)
            }
            if let data = r.secretData {
                if direction == 1 {
                    albumSaveButton("保存到相册", data: data, png: r.png, filename: r.png ? "secret.png" : "secret.jpg")
                    Button("另存为文件") { export(data, type: r.png ? .png : .jpeg, name: r.png ? "secret.png" : "secret.jpg") }
                        .buttonStyle(.bordered).disabled(inputLocked)
                } else {
                    Button("保存处理后的正文图片") { export(data, type: r.png ? .png : .jpeg, name: r.png ? "secret.png" : "secret.jpg") }.buttonStyle(.bordered).disabled(inputLocked)
                }
            }
        }
    }
    private func albumSaveButton(_ title: String, data: Data, png: Bool, filename: String) -> some View {
        Button { savePhotoToAlbum(data, png: png, filename: filename) } label: {
            HStack {
                if savingPhoto { ProgressView().tint(.white) }
                Label(savingPhoto ? "正在保存到相册…" : title, systemImage: "square.and.arrow.down")
            }
        }.buttonStyle(.borderedProminent).disabled(inputLocked)
    }
    private func savePhotoToAlbum(_ data: Data, png: Bool, filename: String) {
        guard !inputLocked else { return }
        savingPhoto = true
        photoSaveNotice = nil
        PhotoLibrarySaver.save(data, png: png, filename: filename) { outcome in
            savingPhoto = false
            switch outcome {
            case .success: photoSaveNotice = "图片已保存到系统相册。"
            case .failure(let failure): error = failure.localizedDescription
            }
        }
    }
    private func export(_ data: Data, type: UTType, name: String) { document = BinaryDocument(data); exportType = type; exportName = name; exporter = true }
    private func run() {
        guard !inputLocked, let carrier, let key = vault.current?.value else { return }
        textFocused = false
        if direction == 0 && mode == 1 && secret == nil { error = "请先选择待加密图片。"; return }
        let decrypt = direction == 1, selectedSecret = mode == 1 ? secret : nil
        let message = text, png = lossless, enhanced = strong
        let flag = CancellationFlag(); job = flag; busy = true; result = nil; progress = 0; status = "正在准备…"
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let callback: BIPProgress = { n, label in
                    guard flag.active else { return false }
                    DispatchQueue.main.async { progress = Double(n) / 100; status = label }
                    return true
                }
                let output: BIPOutput?
                if decrypt { output = try BIPService.decrypt(carrier, key: key, progress: callback) }
                else { output = try BIPService.encrypt(carrier, secret: selectedSecret, text: message, key: key, png: png, strong: enhanced, progress: callback) }
                DispatchQueue.main.async { busy = false; job = nil; if flag.active { result = output; progress = 1; status = "已完成" } else { status = "已取消" } }
            } catch {
                DispatchQueue.main.async { busy = false; job = nil; if flag.active { self.error = error.localizedDescription } else { status = "已取消" } }
            }
        }
    }
}
