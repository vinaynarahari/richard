// swift-tools-version:5.10
import PackageDescription

// Use a single SwiftUI @main entry in RichardMenubarApp.swift.

let package = Package(
    name: "RichardMenubar",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "RichardMenubar", targets: ["RichardMenubar"])
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "RichardMenubar",
            path: "Sources",
            exclude: [
                // Exclude legacy main.swift to avoid @main conflict
                "RichardMenubar/main.swift"
            ],
            sources: [
                "RichardMenubar/RichardMenubarApp.swift",
                "RichardMenubar/StatusBarController.swift",
                "RichardMenubar/AppState.swift",
                "RichardMenubar/APIClient.swift",
                "RichardMenubar/Models.swift",
                "RichardMenubar/RootPopoverView.swift",
                "RichardMenubar/ConnectionsView.swift",
                "RichardMenubar/SettingsView.swift",
                "RichardMenubar/ToastView.swift",
                "RichardMenubar/ChatView.swift",
                "RichardMenubar/_noentry.swift"
                // VoiceView is currently declared inside RootPopoverView.swift for placeholder compilation.
            ],
            resources: []
        )
    ]
)
