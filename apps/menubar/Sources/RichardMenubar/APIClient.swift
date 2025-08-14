import Foundation
import AVFoundation

struct APIClient {
    // IMPORTANT: Use the orchestrator base URL, not Ollama's 11434 port.
    // Default to 127.0.0.1:8000 (uvicorn default when you run without --port 5273).
    private static func defaultBase() -> URL {
        if let s = UserDefaults.standard.string(forKey: "RichardOrchestratorBase"), let u = URL(string: s) {
            return u
        }
        return URL(string: "http://127.0.0.1:8000")!
    }
    let base: URL
    let session: URLSession

    init() {
        // Allow override before init by setting UserDefaults key "RichardOrchestratorBase"
        self.base = APIClient.defaultBase()
        // Ensure timeouts are generous for local model warmup and streaming
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 120
        cfg.timeoutIntervalForResource = 600
        self.session = URLSession(configuration: cfg)
    }

    // MARK: - OAuth/Connections (existing)
    func getOAuthStatus() async throws -> [OAuthStatus] {
        let url = base.appendingPathComponent("/oauth/status")
        let (data, resp) = try await session.data(from: url)
        try ensureOK(resp, data: data)
        return try JSONDecoder().decode([OAuthStatus].self, from: data)
    }

    func getGoogleAuthStartURL() async throws -> URL {
        let url = base.appendingPathComponent("/auth/google/start")
        let (data, resp) = try await session.data(from: url)
        try ensureOK(resp, data: data)
        let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        guard let s = obj?["auth_url"] as? String, let u = URL(string: s) else {
            throw NSError(domain: "API", code: -1, userInfo: [NSLocalizedDescriptionKey: "Invalid auth_url"])
        }
        return u
    }

    func saveNotionToken(_ token: String) async throws {
        let url = base.appendingPathComponent("/dev/notion/save-token")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(["token": token])
        let (data, resp) = try await session.data(for: req)
        try ensureOK(resp, data: data)
    }

    // Restore stubs for ActionsView compatibility (no-ops here; adapt if you still use ActionsView)
    func createCalendarEvent(_ body: CalendarCreateRequest) async throws -> CalendarCreateResponse {
        return CalendarCreateResponse(event_id: nil, htmlLink: nil, status: "unsupported", provider: nil)
    }
    func gmailDraft(_ body: GmailDraftRequest) async throws -> GmailDraftResponse {
        return GmailDraftResponse(draft_id: nil, status: "unsupported", provider: nil)
    }
    func notionCreatePage(_ body: NotionCreateRequest) async throws -> NotionCreateResponse {
        return NotionCreateResponse(page_id: nil, status: "unsupported", provider: nil)
    }

    // MARK: - LLM Chat (SSE streaming)
    struct ChatMessage: Codable {
        let role: String
        let content: String
    }
    enum ChatMode: String, CaseIterable, Identifiable {
        case quick, general, coding, deep
        var id: String { rawValue }
        var label: String {
            switch self {
            case .quick: return "Quick (phi4-mini)"
            case .general: return "General (gemma3n)"
            case .coding: return "Coding (qwen3)"
            case .deep: return "Deep (deepseek-r1)"
            }
        }
    }

    func chatStream(mode: ChatMode, messages: [ChatMessage], remember: Bool, tools: Bool = true) async throws -> AsyncThrowingStream<String, Error> {
        let url = base.appendingPathComponent("/llm/chat")
        var req = URLRequest(url: url)
        req.httpShouldHandleCookies = false
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("keep-alive", forHTTPHeaderField: "Connection")
        req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        req.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        req.setValue("no-cache", forHTTPHeaderField: "Pragma")

        let body: [String: Any] = [
            "mode": mode.rawValue,
            "messages": messages.map { ["role": $0.role, "content": $0.content] },
            "remember": remember,
            "tools": tools
        ]
        req.httpBody = try JSONSerialization.data(withJSONObject: body, options: [])

        let (bytes, resp) = try await session.bytes(for: req)
        try ensureOK(resp)

        return AsyncThrowingStream { continuation in
            Task {
                do {
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data:") else { continue }
                        let jsonPart = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
                        if jsonPart == "[DONE]" { break }
                        if let data = jsonPart.data(using: .utf8),
                           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                            if let t = obj["type"] as? String, t == "token", let content = obj["content"] as? String {
                                continuation.yield(content)
                            }
                            continue
                        }
                        // Fallback: sometimes server streams plain text tokens
                        let fallback = jsonPart
                        if !fallback.isEmpty {
                            continuation.yield(fallback)
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    // MARK: - Voice API
    func startVoiceListening() async throws {
        let url = base.appendingPathComponent("/voice/start")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = [
            "wake_word": "hey richard",
            "enable_tts": true,
            "voice_speed": 1.2
        ] as [String : Any]
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        let (data, resp) = try await session.data(for: req)
        try ensureOK(resp, data: data)
    }
    
    func stopVoiceListening() async throws {
        let url = base.appendingPathComponent("/voice/stop")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        
        let (data, resp) = try await session.data(for: req)
        try ensureOK(resp, data: data)
    }
    
    func getVoiceStatus() async throws -> [String: Any] {
        let url = base.appendingPathComponent("/voice/status")
        let (data, resp) = try await session.data(from: url)
        try ensureOK(resp, data: data)
        return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }
    
    func sendVoiceCommand(_ text: String) async throws {
        let url = base.appendingPathComponent("/voice/command")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = ["text": text]
        req.httpBody = try JSONEncoder().encode(body)
        
        let (data, resp) = try await session.data(for: req)
        try ensureOK(resp, data: data)
    }
    
    func speak(_ text: String) async throws {
        let url = base.appendingPathComponent("/voice/speak")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = ["text": text]
        req.httpBody = try JSONEncoder().encode(body)
        
        let (data, resp) = try await session.data(for: req)
        try ensureOK(resp, data: data)
    }

    func transcribe(audioWavURL: URL, language: String? = nil) async throws -> String {
        let url = base.appendingPathComponent("/voice/transcribe")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"

        // Build multipart/form-data
        let boundary = "Boundary-\(UUID().uuidString)"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var data = Data()
        func appendFormField(name: String, value: String) {
            data.append("--\(boundary)\r\n".data(using: .utf8)!)
            data.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
            data.append("\(value)\r\n".data(using: .utf8)!)
        }

        if let language = language {
            appendFormField(name: "language", value: language)
        }

        let fileData = try Data(contentsOf: audioWavURL)
        data.append("--\(boundary)\r\n".data(using: .utf8)!)
        data.append("Content-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\n".data(using: .utf8)!)
        data.append("Content-Type: audio/wav\r\n\r\n".data(using: .utf8)!)
        data.append(fileData)
        data.append("\r\n".data(using: .utf8)!)
        data.append("--\(boundary)--\r\n".data(using: .utf8)!)

        let (respData, resp) = try await session.upload(for: req, from: data)
        try ensureOK(resp, data: respData)
        let obj = try JSONSerialization.jsonObject(with: respData) as? [String: Any]
        let text = (obj?["text"] as? String) ?? ""
        return text
    }

    // MARK: - Helpers
    private func ensureOK(_ resp: URLResponse, data: Data? = nil) throws {
        guard let http = resp as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            let msg = data.flatMap { String(data: $0, encoding: .utf8) } ?? ""
            throw NSError(domain: NSURLErrorDomain, code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: msg])
        }
    }
}
