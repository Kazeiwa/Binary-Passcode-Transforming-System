import SwiftUI
@main struct BinaryImagePasscodeApp: App {
    @StateObject private var vault = KeyVault()
    @Environment(\.scenePhase) private var phase
    var body: some Scene {
        WindowGroup {
            ContentView().environmentObject(vault)
                .overlay {
                    if phase != .active {
                        Color(.systemBackground).ignoresSafeArea()
                            .overlay { Label("二进制图片密码", systemImage: "lock.shield").font(.title2).foregroundStyle(.teal) }
                    }
                }
                .tint(.teal)
        }
    }
}
