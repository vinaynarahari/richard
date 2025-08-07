import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var state: AppState

    var googleAccounts: [String] {
        state.oauthStatus.first(where: { $0.provider == "google" })?.accounts ?? []
    }

    @State private var wakeWordEnabled = false
    @State private var pttHotkey = "⌥⌘R"

    var body: some View {
        Form {
            Section("Defaults") {
                Picker("Default Google Account", selection: $state.defaultGoogleAccount) {
                    Text("(none)").tag("")
                    ForEach(googleAccounts, id: \.self) { Text($0).tag($0) }
                }
                TextField("Default Notion Parent Page ID", text: $state.defaultNotionParentId)
                Button("Save") { state.saveDefaults(); state.showSuccess("Saved defaults") }
            }
            Section("Voice (coming soon)") {
                Toggle("Enable Wake Word", isOn: $wakeWordEnabled)
                TextField("PTT Hotkey", text: $pttHotkey)
                    .help("Placeholder; will capture a real hotkey in next iteration.")
            }
        }
        .padding()
    }
}
