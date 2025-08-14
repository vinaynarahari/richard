import SwiftUI
import AppKit
import Combine

// Single SwiftUI App entry point. Ensure there are NO other @main or @NSApplicationMain in the target.
@main
struct RichardMenubarApp: App {
    @NSApplicationDelegateAdaptor(AppLifecycle.self) private var appLifecycle

    var body: some Scene {
        // Menubar-only app: provide an empty Settings scene to satisfy App protocol without creating windows.
        Settings {
            EmptyView()
        }
        .commands {
            CommandGroup(replacing: .appSettings) {
                EmptyView()
            }
        }
    }
}


// App lifecycle installs the status bar item and hosts the SwiftUI popover.
// No other entry points exist.
final class AppLifecycle: NSObject, NSApplicationDelegate {
    private var statusBar: StatusBarController?
    private var cancellables = Set<AnyCancellable>()
	    func applicationDidFinishLaunching(_ notification: Notification) {
        let content = RootPopoverView()
            .environmentObject(AppState.shared)
        statusBar = StatusBarController(contentView: content)
        AppState.shared.refreshOAuthStatus()
        
        // Observe voice state changes to update status bar
        setupVoiceStateObservers()
    }
    
    private func setupVoiceStateObservers() {
        let appState = AppState.shared
        
        // Observe recording state
        appState.$isRecording
            .receive(on: DispatchQueue.main)
            .sink { [weak self] isRecording in
                if isRecording {
                    self?.statusBar?.showRecordingIndicator()
                } else {
                    self?.statusBar?.hideRecordingIndicator()
                }
            }
            .store(in: &cancellables)
        
        // Observe wake word detection
        appState.$wakeWordDetected
            .receive(on: DispatchQueue.main)
            .sink { [weak self] detected in
                if detected {
                    self?.statusBar?.showWakeWordIndicator()
                }
            }
            .store(in: &cancellables)
    }
}
