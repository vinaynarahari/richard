import SwiftUI

struct ToastView: View {
    let toast: ToastData
    var body: some View {
        VStack {
            Spacer()
            HStack {
                Image(systemName: toast.isError ? "xmark.octagon.fill" : "checkmark.seal.fill")
                    .foregroundStyle(.white)
                Text(toast.message)
                    .foregroundStyle(.white)
                    .lineLimit(2)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(toast.isError ? Color.red : Color.green)
            .clipShape(Capsule())
            .shadow(radius: 4)
            .padding(.bottom, 10)
        }
        .transition(.move(edge: .bottom).combined(with: .opacity))
        .animation(.easeInOut(duration: 0.25), value: toast.id)
    }
}
