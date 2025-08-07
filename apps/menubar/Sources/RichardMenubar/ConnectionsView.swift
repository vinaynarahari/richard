import SwiftUI

struct ConnectionsView: View {
    @EnvironmentObject var state: AppState
    let api = APIClient()

    @State private var notionToken: String = ""

    var googleAccounts: [String] {
        state.oauthStatus.first(where: { $0.provider == "google" })?.accounts ?? []
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Connections").font(.headline)

            HStack {
                providerChip("Google", connected: !(googleAccounts.isEmpty))
                providerChip("Notion", connected: state.oauthStatus.first(where: { $0.provider == "notion" })?.connected ?? false)
            }

            Divider()

            HStack {
                Button("Connect Google") { connectGoogle() }
                Spacer()
                Text(googleAccounts.joined(separator: ", "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            HStack {
                TextField("Notion Internal Integration Token", text: $notionToken)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { saveNotionToken() }
                Button("Save Notion Token") { saveNotionToken() }
            }

            Spacer()
        }
        .padding()
    }

    private func connectGoogle() {
        Task {
            do {
                let url = try await api.getGoogleAuthStartURL()
                NSWorkspace.shared.open(url)
                state.showSuccess("Opened Google consent in your browser.")
            } catch {
                state.showError("Google start failed: \(error.localizedDescription)")
            }
        }
    }

    private func saveNotionToken() {
        Task {
            let token = notionToken.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !token.isEmpty else {
                state.showError("Enter a Notion token.")
                return
            }
            do {
                try await api.saveNotionToken(token)
                state.showSuccess("Saved Notion token")
                state.refreshOAuthStatus()
            } catch {
                state.showError("Save token failed: \(error.localizedDescription)")
            }
        }
    }

    @ViewBuilder
    private func providerChip(_ name: String, connected: Bool) -> some View {
        HStack {
            Circle().fill(connected ? .green : .red).frame(width: 10, height: 10)
            Text(name)
        }
        .padding(6)
        .background(.thinMaterial)
        .clipShape(Capsule())
    }
}
