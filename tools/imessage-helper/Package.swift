// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "imessage-helper",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "imessage-helper", targets: ["IMHelper"])
    ],
    targets: [
        .executableTarget(
            name: "IMHelper",
            path: "Sources/IMHelper"
        )
    ]
)
