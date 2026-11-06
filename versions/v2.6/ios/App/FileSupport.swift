import SwiftUI
import UniformTypeIdentifiers
import ImageIO
import UIKit

enum TextCodec {
    static func count(_ text: String) throws -> Int {
        var failure: NSError?
        let count = BIPService.unitCount(text, error: &failure)
        if let failure { throw failure }
        guard count >= 0 else { throw VaultError(message: "正文编码失败，请检查输入内容。") }
        return count
    }
}

func previewImage(_ data: Data, maxPixel: Int = 1200) -> UIImage? {
    guard let source = CGImageSourceCreateWithData(data as CFData, nil),
          let cg = CGImageSourceCreateThumbnailAtIndex(source, 0, [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maxPixel
          ] as CFDictionary) else { return nil }
    return UIImage(cgImage: cg)
}
struct BinaryDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.data] }
    var data: Data
    init(_ data: Data) { self.data = data }
    init(configuration: ReadConfiguration) throws { data = configuration.file.regularFileContents ?? Data() }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: data) }
}
func readSelectedFile(_ url: URL, limit: Int = 150 * 1024 * 1024) throws -> Data {
    let scoped = url.startAccessingSecurityScopedResource()
    defer { if scoped { url.stopAccessingSecurityScopedResource() } }
    // NSFileCoordinator also handles cloud-backed files selected through Files.
    var accessError: NSError?, readError: Error?, result: Data?
    NSFileCoordinator().coordinate(readingItemAt: url, options: [], error: &accessError) { local in
        do {
            let size = try local.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
            guard size <= limit else { throw VaultError(message: "文件过大，请选择较小的图片或备份文件。") }
            let handle = try FileHandle(forReadingFrom: local)
            defer { try? handle.close() }
            let data = try handle.read(upToCount: limit + 1) ?? Data()
            guard !data.isEmpty, data.count <= limit else { throw VaultError(message: "文件为空或超过大小限制。") }
            result = data
        } catch { readError = error }
    }
    if let accessError { throw accessError }
    if let readError { throw readError }
    guard let result else { throw VaultError(message: "无法读取所选文件。") }
    return result
}
final class CancellationFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false
    func cancel() { lock.lock(); cancelled = true; lock.unlock() }
    var active: Bool { lock.lock(); defer { lock.unlock() }; return !cancelled }
}
func secondsDate(_ seconds: UInt64) -> String {
    let f = DateFormatter(); f.locale = Locale(identifier: "zh_CN"); f.timeZone = TimeZone(secondsFromGMT: 8 * 3600)
    f.dateFormat = "yyyy-MM-dd HH:mm:ss"
    return f.string(from: Date(timeIntervalSince1970: TimeInterval(seconds))) + "（北京时间）"
}
