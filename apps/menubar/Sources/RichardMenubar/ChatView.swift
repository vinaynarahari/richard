import SwiftUI
import Combine
import AppKit

struct ChatMessageRow: Identifiable {
    let id = UUID()
    let role: String   // "user" or "assistant"
    let content: String
}

struct ChatView: View {
    @EnvironmentObject var state: AppState
    let api = APIClient()

    @State private var mode: APIClient.ChatMode = .general
    @State private var input: String = ""
    @State private var messages: [ChatMessageRow] = []
    @State private var remember: Bool = false
    @State private var isStreaming = false
    @State private var streamTask: Task<Void, Never>? = nil
    @State private var inactivityTimer: Timer? = nil
    @State private var lastInteractionTime = Date()

    // DEBUG: persistent diagnostics for last request/response
    @State private var showDebug = false
    @State private var lastRequestJSON = ""
    @State private var lastStatus = ""
    @State private var lastErrorText = ""
    // Strict mode: only allow responses from orchestrator (127.0.0.1:5273)
    @State private var strictMode = true

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            header
            if showDebug { debugPane }
            conversationList
            composer
        }
        .padding()
        .onDisappear { 
            cancelStream()
            stopInactivityTimer()
        }
        .onAppear {
            startInactivityTimer()
        }
    }

    // MARK: - Subviews

    private var header: some View {
        HStack {
            Picker("Mode", selection: $mode) {
                ForEach(APIClient.ChatMode.allCases) { m in
                    Text(m.label).tag(m)
                }
            }
            .pickerStyle(.menu)

            Toggle("Remember this", isOn: $remember)
                .toggleStyle(.switch)

            Button(showDebug ? "Hide Debug" : "Show Debug") {
                showDebug.toggle()
            }
            Toggle("Strict", isOn: $strictMode)
                .help("When enabled, blocks any response not from 127.0.0.1:5273")

            Button("Test") {
                input = "hi"
                send()
            }
            .disabled(isStreaming)
            .help("Sends a minimal quick test after pre-warming models.")
        }
    }

    private var debugPane: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Debug").font(.caption).foregroundColor(.secondary)
            HStack(spacing: 12) {
                Label(strictMode ? "Strict: ON" : "Strict: OFF", systemImage: strictMode ? "lock.fill" : "lock.open")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(strictMode ? .green : .orange)
                if !lastStatus.isEmpty {
                    Text("Status: \(lastStatus)").font(.system(size: 11, weight: .semibold))
                }
            }
            if !lastStatus.isEmpty {
                Text("Status: \(lastStatus)").font(.system(size: 11, weight: .semibold))
            }
            if !lastRequestJSON.isEmpty {
                Text("Request JSON:")
                    .font(.system(size: 11, weight: .semibold))
                ScrollView {
                    Text(lastRequestJSON)
                        .font(.system(size: 11, design: .monospaced))
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(height: 60)
                .background(Color.gray.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }
            if !lastErrorText.isEmpty {
                Text("Response/Error:")
                    .font(.system(size: 11, weight: .semibold))
                ScrollView {
                    Text(lastErrorText)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(height: 60)
                .background(Color.red.opacity(0.06))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }
            HStack {
                Spacer()
                Button("Clear Debug") {
                    lastStatus = ""
                    lastErrorText = ""
                    lastRequestJSON = ""
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(8)
        .background(Color.yellow.opacity(0.07))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private var conversationList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(messages) { msg in
                        messageRow(msg)
                            .id(msg.id)
                    }
                }
                .padding(.vertical, 6)
            }
            .frame(minHeight: 240, maxHeight: 300)
            .onChange(of: messages.count) { _ in
                if let last = messages.last {
                    proxy.scrollTo(last.id, anchor: .bottom)
                }
            }
        }
    }

    @ViewBuilder
    private func messageRow(_ msg: ChatMessageRow) -> some View {
        HStack(alignment: .top) {
            Text(msg.role == "user" ? "You" : "Richard")
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundColor(msg.role == "user" ? Color.secondary : Color.blue)
                .frame(width: 56, alignment: .leading)
            Text(msg.content)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .background(msg.role == "user" ? Color.gray.opacity(0.12) : Color.blue.opacity(0.10))
                .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    private var composer: some View {
        HStack(spacing: 8) {
            TextField("Type a message…", text: $input, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .onSubmit {
                    // Simple approach: onSubmit handles Enter, Shift+Enter is handled by TextField naturally
                    if isStreaming { cancelStream() } else { send() }
                }
            Button(isStreaming ? "Stop" : "Send") {
                if isStreaming { cancelStream() } else { send() }
            }
            .keyboardShortcut(.return, modifiers: [.command])
            .disabled(isStreaming || input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
    }

    // MARK: - Actions

    private func cancelStream() {
        streamTask?.cancel()
        streamTask = nil
        isStreaming = false
    }

    private func send() {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        // Build request JSON exactly like the curl that works and show it in debug
        let msgArray: [[String: String]] = [["role": "user", "content": text]]
        let reqObj: [String: Any] = [
            "mode": mode.rawValue,
            "messages": msgArray,
            "remember": remember,
            "tools": true
        ]
        if let data = try? JSONSerialization.data(withJSONObject: reqObj, options: [.prettyPrinted]),
           let s = String(data: data, encoding: .utf8) {
            lastRequestJSON = s
        } else {
            lastRequestJSON = "(unable to encode request)"
        }

        // Append user message to conversation and clear input
        messages.append(.init(role: "user", content: text))
        input = ""

        // Start assistant placeholder which we will stream into
        var assistantIndex: Int?
        let placeholder = ChatMessageRow(role: "assistant", content: "")
        messages.append(placeholder)
        assistantIndex = messages.count - 1

        isStreaming = true
        lastStatus = "sending…"
        lastErrorText = ""

        let msgs: [APIClient.ChatMessage] = [.init(role: "user", content: text)]

        streamTask = Task {
            do {
                let stream = try await api.chatStream(mode: mode, messages: msgs, remember: remember, tools: true)
                lastStatus = "streaming"
                // Strict response origin enforcement via a marker token we set in API client errors
                for try await token in stream {
                    if strictMode, token == "__SOURCE_PORT_11434__" {
                        // Abort streaming; surface explicit message and stop.
                        lastStatus = "blocked (11434)"
                        lastErrorText = "Blocked response from non-orchestrator port 11434. Ensure only FastAPI (127.0.0.1:5273) is being called."
                        state.showError("Blocked non-orchestrator response (11434).")
                        break
                    }
                    if let idx = assistantIndex {
                        let current = messages[idx].content
                        messages[idx] = ChatMessageRow(role: "assistant", content: current + token)
                    }
                }
                isStreaming = false
                lastStatus = "done"
                state.showSuccess("Reply finished")
            } catch {
                isStreaming = false
                let ns = error as NSError
                let message = ns.userInfo[NSLocalizedDescriptionKey] as? String ?? error.localizedDescription
                lastStatus = "error \(ns.code)"
                lastErrorText = message
                state.showError("Chat error: \(message)")
                print("[ChatView] chatStream failed: domain=\(ns.domain) code=\(ns.code) message=\(message)")
            }
        }
        
        // Update interaction time on user activity
        lastInteractionTime = Date()
        resetInactivityTimer()
    }
    
    // MARK: - Inactivity Timer
    
    private func startInactivityTimer() {
        resetInactivityTimer()
    }
    
    private func resetInactivityTimer() {
        stopInactivityTimer()
        inactivityTimer = Timer.scheduledTimer(withTimeInterval: 300, repeats: false) { _ in
            // Clear chat after 5 minutes of inactivity
            clearChat()
        }
    }
    
    private func stopInactivityTimer() {
        inactivityTimer?.invalidate()
        inactivityTimer = nil
    }
    
    private func clearChat() {
        messages.removeAll()
        lastStatus = "cleared (5min inactive)"
        print("[ChatView] Chat cleared after 5 minutes of inactivity")
    }
}
