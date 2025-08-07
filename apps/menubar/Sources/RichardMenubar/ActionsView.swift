import SwiftUI

// Disabled for now; Actions were superseded by Chat. Keep a minimal stub so the project compiles.
struct ActionsView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Actions (disabled)")
                .font(.headline)
            Text("This panel has been replaced by Chat. We’ll restore individual actions in a later iteration.")
                .font(.caption)
                .foregroundColor(.secondary)
            Spacer()
        }
        .padding()
    }
}
