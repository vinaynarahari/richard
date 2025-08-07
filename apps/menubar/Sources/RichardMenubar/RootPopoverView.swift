import SwiftUI

struct RootPopoverView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        ZStack {
            TabView {
                // Replace Actions with Chat
                ChatView()
                    .tabItem { Label("Chat", systemImage: "message.fill") }

                ConnectionsView()
                    .tabItem { Label("Connections", systemImage: "link") }

                // Add Voice tab placeholder (will implement next)
                VoiceView()
                    .tabItem { Label("Voice", systemImage: "waveform") }

                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gearshape") }
            }
            .frame(minWidth: 400, minHeight: 480)
            .task { state.refreshOAuthStatus() }

            if let toast = state.toast {
                ToastView(toast: toast)
                    .onAppear {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2.4) { state.toast = nil }
                    }
            }
        }
    }
}

// Minimal VoiceView implementation so the project compiles; full mic pipeline to follow.
struct VoiceView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Voice").font(.headline)
            Text("Push-to-talk and TTS will be added next.").foregroundStyle(.secondary)
        }
        .padding()
    }
}
