import Foundation
import Combine

final class AppState: ObservableObject {
    static let shared = AppState()

    @Published var oauthStatus: [OAuthStatus] = []
    @Published var defaultGoogleAccount: String = UserDefaults.standard.string(forKey: "defaultGoogleAccount") ?? ""
    @Published var defaultNotionParentId: String = UserDefaults.standard.string(forKey: "defaultNotionParentId") ?? ""
    @Published var toast: ToastData? = nil

    // Voice state
    @Published var isVoiceListening: Bool = false
    @Published var isRecording: Bool = false
    @Published var isProcessingVoice: Bool = false
    @Published var lastTranscription: String = ""
    @Published var voiceResponse: String = ""
    @Published var wakeWordDetected: Bool = false

    // Trigger to force refresh across views
    @Published var triggerRefresh: Bool = false

    private var cancellables = Set<AnyCancellable>()
    private let api = APIClient()

    init() {
        refreshOAuthStatus()
    }

    func refreshOAuthStatus() {
        Task { @MainActor in
            do {
                let status = try await api.getOAuthStatus()
                self.oauthStatus = status
                self.triggerRefresh.toggle()
            } catch {
                // Tolerate missing oauth route: if 404, treat as empty providers and proceed silently
                let ns = error as NSError
                if ns.domain == "API", ns.code == 404 || ns.code == 405 {
                    self.oauthStatus = []
                    self.triggerRefresh.toggle()
                } else {
                    self.toast = .error("Failed to load status: \(error.localizedDescription)")
                }
            }
        }
    }

    func saveDefaults() {
        UserDefaults.standard.set(defaultGoogleAccount, forKey: "defaultGoogleAccount")
        UserDefaults.standard.set(defaultNotionParentId, forKey: "defaultNotionParentId")
    }

    // MARK: - Voice Controls
    func startVoiceListening() {
        Task { @MainActor in
            do {
                try await api.startVoiceListening()
                isVoiceListening = true
                showSuccess("Voice listening started - say 'Hey Richard'")
            } catch {
                showError("Failed to start voice listening: \(error.localizedDescription)")
            }
        }
    }
    
    func stopVoiceListening() {
        Task { @MainActor in
            do {
                try await api.stopVoiceListening()
                isVoiceListening = false
                isRecording = false
                wakeWordDetected = false
                showSuccess("Voice listening stopped")
            } catch {
                showError("Failed to stop voice listening: \(error.localizedDescription)")
            }
        }
    }
    
    func simulateWakeWord() {
        wakeWordDetected = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            self.wakeWordDetected = false
        }
    }

    func showSuccess(_ msg: String) { toast = .success(msg) }
    func showError(_ msg: String) { toast = .error(msg) }
}

struct ToastData: Identifiable {
    let id = UUID()
    let message: String
    let isError: Bool

    static func success(_ m: String) -> ToastData { .init(message: m, isError: false) }
    static func error(_ m: String) -> ToastData { .init(message: m, isError: true) }
}
