import SwiftUI
import AppKit

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

    func applicationDidFinishLaunching(_ notification: Notification) {
        let content = RootPopoverView()
            .environmentObject(AppState.shared)
        statusBar = StatusBarController(contentView: content)
        AppState.shared.refreshOAuthStatus()
    }
}
