import Foundation
import Photos

enum PhotoLibrarySaver {
    /// Add the file bytes directly, retaining the original JPG/PNG resource.
    /// Add-only authorization does not grant access to the user's existing photos.
    static func save(_ data: Data, png: Bool, filename: String? = nil, completion: @escaping (Result<Void, Error>) -> Void) {
        let finish: (Result<Void, Error>) -> Void = { outcome in
            DispatchQueue.main.async { completion(outcome) }
        }
        guard !data.isEmpty else {
            finish(.failure(VaultError(message: "没有可以保存的图片，请先完成加密或解密。")))
            return
        }
        let write = {
            PHPhotoLibrary.shared().performChanges({
                let options = PHAssetResourceCreationOptions()
                options.originalFilename = filename ?? (png ? "secret.png" : "secret.jpg")
                let request = PHAssetCreationRequest.forAsset()
                request.addResource(with: .photo, data: data, options: options)
            }, completionHandler: { success, error in
                if success { finish(.success(Void())) }
                else {
                    let detail = error.map { "：" + $0.localizedDescription } ?? "，请稍后重试。"
                    finish(.failure(VaultError(message: "保存到相册失败" + detail)))
                }
            })
        }
        let authorize: (PHAuthorizationStatus) -> Void = { status in
            switch status {
            case .authorized, .limited: write()
            case .denied, .restricted:
                finish(.failure(VaultError(message: "未获准向相册添加图片。请在系统设置中允许本应用添加照片，或选择“另存为文件”。")))
            case .notDetermined:
                finish(.failure(VaultError(message: "尚未完成相册保存授权，请再次点击保存并选择允许。")))
            @unknown default:
                finish(.failure(VaultError(message: "当前无法向相册添加图片，请选择“另存为文件”。")))
            }
        }
        let status = PHPhotoLibrary.authorizationStatus(for: .addOnly)
        if status == .notDetermined { PHPhotoLibrary.requestAuthorization(for: .addOnly, handler: authorize) }
        else { authorize(status) }
    }
}
