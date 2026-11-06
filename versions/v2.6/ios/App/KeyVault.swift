import Foundation
import Combine
import Security
import CryptoKit

struct SavedKey: Codable, Identifiable {
    let id: UUID
    var name: String
    let value: String
}
struct VaultError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}
@MainActor final class KeyVault: ObservableObject {
    @Published private(set) var keys: [SavedKey] = []
    @Published var selected: UUID? {
        didSet { UserDefaults.standard.set(selected?.uuidString, forKey: "selectedKeyID") }
    }
    private let service = "org.binarypasscode.image.ios.keys.v1"
    private var loaded = false
    var current: SavedKey? { keys.first { $0.id == selected } }
    init() { selected = UserDefaults.standard.string(forKey: "selectedKeyID").flatMap(UUID.init(uuidString:)) }
    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service, kSecAttrAccount as String: "vault",
         kSecAttrSynchronizable as String: false]
    }
    func load() throws {
        var q = query; q[kSecReturnData as String] = true; q[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &result)
        if status == errSecItemNotFound { keys = []; loaded = true; return }
        guard status == errSecSuccess, let data = result as? Data else {
            throw VaultError(message: "无法打开本地密钥。请解锁设备后重试。（\(status)）")
        }
        let records = try JSONDecoder().decode([SavedKey].self, from: data)
        try validate(records)
        keys = records; loaded = true
        if current == nil { selected = keys.first?.id }
    }
    private func validate(_ records: [SavedKey]) throws {
        guard records.count <= 1000,
              Set(records.map(\.id)).count == records.count,
              Set(records.map(\.name)).count == records.count,
              records.allSatisfy({ !$0.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && $0.name.count <= 80 && Self.valid($0.value) }) else {
            throw VaultError(message: "密钥库格式无效。原有密钥不会被覆盖。")
        }
    }
    static func valid(_ value: String) -> Bool { value.utf8.count == 128 && value.utf8.allSatisfy { $0 >= 48 && $0 <= 57 } }
    private func commit(_ records: [SavedKey]) throws {
        guard loaded else { throw VaultError(message: "密钥库尚未成功打开，请先重试打开。") }
        try validate(records)
        let data = try JSONEncoder().encode(records)
        let attrs: [String: Any] = [kSecValueData as String: data,
                                    kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        var status = SecItemUpdate(query as CFDictionary, attrs as CFDictionary)
        if status == errSecItemNotFound {
            status = SecItemAdd(query.merging(attrs) { _, new in new } as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw VaultError(message: "密钥保存失败，原有数据保留。（\(status)）") }
        keys = records
        if current == nil { selected = keys.first?.id }
    }
    func add(name: String, value: String) throws {
        guard Self.valid(value) else { throw VaultError(message: "密钥必须为128位半角数字，前导零必须保留。") }
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !keys.contains(where: { $0.name == name }) else { throw VaultError(message: "密钥名称已存在，请换一个名称。") }
        let item = SavedKey(id: UUID(), name: name, value: value)
        try commit(keys + [item]); selected = item.id
    }
    func delete(_ id: UUID) throws { try commit(keys.filter { $0.id != id }) }
    func rename(_ id: UUID, to name: String) throws {
        var copy = keys
        guard let i = copy.firstIndex(where: { $0.id == id }) else { return }
        copy[i].name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        try commit(copy)
    }
    func export(password: String) throws -> Data {
        guard loaded, !keys.isEmpty, password.count >= 10 else {
            throw VaultError(message: "请先保存密钥，并设置至少10个字符的备份密码。")
        }
        var salt = Data(count: 16)
        let status = salt.withUnsafeMutableBytes { SecRandomCopyBytes(kSecRandomDefault, 16, $0.baseAddress!) }
        guard status == errSecSuccess else { throw VaultError(message: "无法生成安全随机数。") }
        let derived: Data? = try BIPService.backupKey(password, salt: salt)
        guard let key = derived else { throw VaultError(message: "备份失败。") }
        let payload = try JSONEncoder().encode(keys)
        let box = try AES.GCM.seal(payload, using: SymmetricKey(data: key))
        guard let combined = box.combined else { throw VaultError(message: "备份失败。") }
        return Data("BIPIK1".utf8) + salt + combined
    }
    func restore(_ data: Data, password: String) throws {
        guard loaded, data.count >= 50, data.count <= 2_000_000, data.prefix(6) == Data("BIPIK1".utf8) else {
            throw VaultError(message: "这不是有效的iOS密钥备份。")
        }
        do {
            let derived: Data? = try BIPService.backupKey(password, salt: data.subdata(in: 6..<22))
            guard let key = derived else {
                throw VaultError(message: "无法处理备份密码。")
            }
            let box = try AES.GCM.SealedBox(combined: data.dropFirst(22))
            let plain = try AES.GCM.open(box, using: SymmetricKey(data: key))
            let imported = try JSONDecoder().decode([SavedKey].self, from: plain)
            try validate(imported)
            var merged = keys
            for record in imported {
                if merged.contains(where: { $0.value == record.value }) { continue }
                var name = record.name, n = 2
                while merged.contains(where: { $0.name == name }) { name = "\(record.name.prefix(65)) (\(n))"; n += 1 }
                merged.append(SavedKey(id: UUID(), name: name, value: record.value))
            }
            try commit(merged)
        } catch let error as VaultError { throw error }
        catch { throw VaultError(message: "无法恢复备份：密码不正确，或文件已损坏。原有密钥保留。") }
    }
}
