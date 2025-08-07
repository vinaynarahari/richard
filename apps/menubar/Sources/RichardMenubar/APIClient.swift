import Foundation
import AVFoundation

struct APIClient {
    // IMPORTANT: Use the orchestrator base URL, not Ollama's 11434 port.
    // The app must POST to FastAPI at 127.0.0.1:5273/llm/chat which proxies to Ollama.
    let base = URL(string: "http://127.0.0.1:5273")!
    let session: URLSession

    init() {
        // Ensure timeouts are generous for local model warmup and streaming
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 120
        cfg.timeoutIntervalForResource = 600
        // Do NOT set waitsForConnectivity for localhost; it may cause GET probes on retry paths.
        // Use a plain session; we removed RedirectBlocker for build stability.
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
            case .quick: return "Quick (phi3:latest)"
            case .general: return "General (gemma3n)"
            case .coding: return "Coding (qwen3)"
            case .deep: return "Deep (deepseek-r1)"
            }
        }
    }

    func chatStream(mode: ChatMode, messages: [ChatMessage], remember: Bool, tools: Bool = true) async throws -> AsyncThrowingStream<String, Error> {
        // STRICT GUARD: refuse to run if base is not the orchestrator endpoint.
        guard base.scheme == "http",
              base.host == "127.0.0.1",
              base.port == 5273 else {
            throw NSError(domain: "API", code: 400, userInfo: [NSLocalizedDescriptionKey: "Invalid base URL: expected http://127.0.0.1:5273 (orchestrator). Got \(base.absoluteString)"])
        }

        // Ensure we hit the orchestrator and not Ollama directly.
        // Also explicitly disallow redirection that might switch to GET.
        let url = base.appendingPathComponent("/llm/chat")
        var req = URLRequest(url: url)
        req.httpShouldHandleCookies = false
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // Explicitly prefer keeping the connection alive for SSE
        req.setValue("keep-alive", forHTTPHeaderField: "Connection")
        req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        // Prevent proxies or frameworks from attempting to preflight/follow with GET
        req.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        req.setValue("no-cache", forHTTPHeaderField: "Pragma")
        // Pin Host header explicitly (some proxies infer 11434 otherwise)
        req.setValue("127.0.0.1:5273", forHTTPHeaderField: "Host")

        let body: [String: Any] = [
            "mode": mode.rawValue,
            "messages": messages.map { ["role": $0.role, "content": $0.content] },
            "remember": remember,
            "tools": tools
        ]
        req.httpBody = try JSONSerialization.data(withJSONObject: body, options: [])

        // Start the request and get async bytes
        let (bytes, resp) = try await session.bytes(for: req)
        // Defensive: assert we didn't accidentally hit Ollama on 11434 (would 400 with html/json error).
        if let r = resp.url, r.port == 11434 || r.absoluteString.contains("://127.0.0.1:11434") {
            // Yield a special marker first so UI can stop, then throw with clear reason.
            return AsyncThrowingStream { continuation in
                continuation.yield("__SOURCE_PORT_11434__")
                continuation.finish(throwing: NSError(domain: "API",
                                                      code: 400,
                                                      userInfo: [NSLocalizedDescriptionKey: "Blocked: response came from 127.0.0.1:11434 (Ollama). Expected orchestrator 127.0.0.1:5273. Close any tools hitting 11434 and retry."]))
            }
        }
        guard let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            // Fallback: read a small buffer manually since AsyncBytes has no 'collect' on older SDKs
            var accumulator = Data()
            var iterator = bytes.makeAsyncIterator()
            // Try to read up to 4KB error body; stop early if not available
            var count = 0
            while let b = try await iterator.next(), count < 4096 {
                accumulator.append(b)
                count += 1
            }

            let errText = String(data: accumulator, encoding: .utf8) ?? "HTTP error"
            throw NSError(domain: "API", code: (resp as? HTTPURLResponse)?.statusCode ?? -1, userInfo: [NSLocalizedDescriptionKey: errText])
        }

        // Stream tokens from SSE lines:
        return AsyncThrowingStream { continuation in
            Task {
                do {
                    for try await line in bytes.lines {
                        // Some stacks emit keepalive blank lines
                        guard !line.isEmpty else { continue }
                        guard line.hasPrefix("data:") else { continue }
                        let payload = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
                        if payload == "[DONE]" {
                            break
                        }
                        if let data = payload.data(using: .utf8),
                           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                            if let t = obj["type"] as? String, t == "token", let content = obj["content"] as? String {
                                continuation.yield(content)
                            } else if let t = obj["type"] as? String, t == "meta" {
                                // ignore meta in UI
                            } else if let t = obj["type"] as? String, t == "error" {
                                let msg = (obj["error"] as? String) ?? "Unknown error"
                                throw NSError(domain: "SSE", code: -1, userInfo: [NSLocalizedDescriptionKey: msg])
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    // MARK: - Voice transcription
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
    private func ensureOK(_ resp: URLResponse, data: Data) throws {
        if let http = resp as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            let s = String(data: data, encoding: .utf8) ?? ""
            throw NSError(domain: "API", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: s])
        }
    }
}
