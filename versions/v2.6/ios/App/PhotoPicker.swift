import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

struct PickedPhoto {
    let data: Data
    let name: String
}

/// The system picker grants access only to the selected photo. Request its file
/// representation instead of loading/re-encoding UIImage, preserving PNG parity.
struct PhotoPicker: UIViewControllerRepresentable {
    let onStart: () -> Void
    let onFinish: (Result<PickedPhoto, Error>?) -> Void

    func makeUIViewController(context: Context) -> PHPickerViewController {
        var configuration = PHPickerConfiguration()
        configuration.filter = .images
        configuration.selectionLimit = 1
        configuration.preferredAssetRepresentationMode = .current
        let picker = PHPickerViewController(configuration: configuration)
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ picker: PHPickerViewController, context: Context) {
        context.coordinator.parent = self
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        var parent: PhotoPicker
        init(_ parent: PhotoPicker) { self.parent = parent }

        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            guard let result = results.first else { parent.onFinish(nil); return }
            let provider = result.itemProvider
            guard let identifier = provider.registeredTypeIdentifiers.first(where: {
                UTType($0)?.conforms(to: .image) == true
            }) else {
                parent.onFinish(.failure(VaultError(message: "无法读取所选相册图片，请尝试从文件选择。")))
                return
            }
            parent.onStart()
            let finish = parent.onFinish
            let suggestedName = provider.suggestedName
            provider.loadFileRepresentation(forTypeIdentifier: identifier) { url, error in
                let outcome: Result<PickedPhoto, Error>
                do {
                    if let error { throw VaultError(message: "相册图片读取失败：" + error.localizedDescription) }
                    guard let url else { throw VaultError(message: "无法取得相册图片，请确认图片已从iCloud下载完成。") }
                    // The provider's URL is valid only during this callback. Read
                    // the bytes here, not after dispatching back to the main queue.
                    let data = try readSelectedFile(url)
                    var name = suggestedName.flatMap { $0.isEmpty ? nil : $0 } ?? "相册图片"
                    if (name as NSString).pathExtension.isEmpty,
                       let ext = UTType(identifier)?.preferredFilenameExtension { name += "." + ext }
                    outcome = .success(PickedPhoto(data: data, name: name))
                } catch { outcome = .failure(error) }
                DispatchQueue.main.async { finish(outcome) }
            }
        }
    }
}
