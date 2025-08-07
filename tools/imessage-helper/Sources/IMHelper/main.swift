import Foundation
import SQLite3

// Provide SQLITE_TRANSIENT for sqlite3_bind_text in Swift
private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

// Simple JSON protocol over stdin/stdout
// Requests:
//  { "action": "resolve", "query": "D1 Haters" }
//  { "action": "send", "chat_id": "iMessage;-;XXXXXXXX", "body": "..." }
//  { "action": "send", "to": ["+14155551234","name@example.com"], "body": "..." }
//
// Responses:
//  resolve -> { "status":"ok", "results":[ { "chat_id":"...", "display_name":"...", "participants":[...] } ] }
//  send    -> { "status":"sent", "detail":"...", "chat_id":"...", "to":[...] } | { "status":"error", "error":"..." }

struct ResolveRequest: Codable {
    let action: String
    let query: String?
}

struct SendRequest: Codable {
    let action: String
    let chat_id: String?
    let to: [String]?
    let body: String?
}

struct ResolveResult: Codable {
    let chat_id: String              // Primary id to target (prefer scriptable guid "*;-;*"; else chat_identifier/guid)
    let display_name: String?
    let participants: [String]       // Participants for fallback
    let chat_guid: String?           // DB chat.guid (may be scriptable)
    let chat_identifier: String?     // DB chat.chat_identifier (often "chat###")
}

struct ResolveResponse: Codable {
    let status: String
    let results: [ResolveResult]
}

struct SendResponse: Codable {
    let status: String
    let detail: String?
    let chat_id: String?
    let to: [String]?
    let error: String?
}

enum HelperError: Error {
    case invalidInput(String)
    case sqlite(String)
    case sendFailed(String)
    case notFound
}

final class ChatResolver {
    private let dbPath: String

    init(dbPath: String = NSHomeDirectory() + "/Library/Messages/chat.db") {
        self.dbPath = dbPath
    }

    func resolve(query: String) throws -> [ResolveResult] {
        var db: OpaquePointer?
        guard sqlite3_open(dbPath, &db) == SQLITE_OK, let db = db else {
            throw HelperError.sqlite("Failed to open chat.db at \(dbPath)")
        }
        defer { sqlite3_close(db) }

        // We will look for matches in chat.display_name and in handle.id for participants
        // Schema references:
        // - chat (ROWID, guid, chat_identifier, display_name)
        // - chat_handle_join (chat_id, handle_id)
        // - handle (ROWID, id)
        // Prefer a guid that matches "*;-;*" (scriptable), else fall back to chat_identifier or guid, but always return participants.
        let sql = """
        SELECT c.guid, c.chat_identifier, c.display_name,
               GROUP_CONCAT(h.id, ',') AS participants
        FROM chat c
        LEFT JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
        LEFT JOIN handle h ON h.ROWID = chj.handle_id
        WHERE (c.display_name LIKE ?1)
           OR (h.id LIKE ?1)
           OR (c.chat_identifier LIKE ?1)
           OR (c.guid LIKE ?1)
        GROUP BY c.guid, c.chat_identifier, c.display_name
        ORDER BY CASE
           WHEN c.display_name = ?2 THEN 0
           WHEN c.display_name LIKE ?3 THEN 1
           ELSE 2
        END, c.ROWID DESC
        LIMIT 20;
        """

        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let stmtUnwrapped = stmt else {
            throw HelperError.sqlite("Failed to prepare statement")
        }
        defer { sqlite3_finalize(stmtUnwrapped) }

        let like = "%\(query)%"
        // Bind parameters: ?1 = %query%, ?2 = exact, ?3 = prefix match "query%"
        sqlite3_bind_text(stmtUnwrapped, 1, (like as NSString).utf8String, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(stmtUnwrapped, 2, (query as NSString).utf8String, -1, SQLITE_TRANSIENT)
        let prefix = "\(query)%"
        sqlite3_bind_text(stmtUnwrapped, 3, (prefix as NSString).utf8String, -1, SQLITE_TRANSIENT)

        var results: [ResolveResult] = []
        while sqlite3_step(stmtUnwrapped) == SQLITE_ROW {
            let guid = String(cString: sqlite3_column_text(stmtUnwrapped, 0))
            let chatIdentifier = String(cString: sqlite3_column_text(stmtUnwrapped, 1))
            let displayNameC = sqlite3_column_text(stmtUnwrapped, 2)
            let displayName = displayNameC != nil ? String(cString: displayNameC!) : nil
            let participantsC = sqlite3_column_text(stmtUnwrapped, 3)
            let participants = participantsC != nil ? String(cString: participantsC!).split(separator: ",").map { String($0) } : []

            // Choose a scriptable chat id if available (e.g., "iMessage;-;XXXX" or "SMS;-;XXXX")
            let isGuidScriptable = (guid.range(of: "^[A-Za-z]+;-;.+$", options: .regularExpression) != nil)
            let isIdentScriptable = (chatIdentifier.range(of: "^[A-Za-z]+;-;.+$", options: .regularExpression) != nil)

            let chatId: String
            if isIdentScriptable {
                chatId = chatIdentifier
            } else if isGuidScriptable {
                chatId = guid
            } else if !chatIdentifier.isEmpty {
                chatId = chatIdentifier // DB-specific id (might be "chat123...")
            } else {
                chatId = guid // last resort
            }

            results.append(ResolveResult(
                chat_id: chatId,
                display_name: displayName,
                participants: participants,
                chat_guid: guid.isEmpty ? nil : guid,
                chat_identifier: chatIdentifier.isEmpty ? nil : chatIdentifier
            ))
        }
        return results
    }
}

final class IMessenger {
    // Use NSAppleScript as a fallback to target chat by id or buddy id directly.
    // We avoid enumerating services/accounts due to -1728 issues on some macOS builds.
    func sendToChatIdOrParticipants(_ chatId: String, participants: [String], body: String, displayName: String? = nil) throws {
        // If chatId is in scriptable form "*;-;*", send directly to chat id.
        if chatId.range(of: "^[A-Za-z]+;-;.+$", options: .regularExpression) != nil {
            let script = """
            on run argv
              set msg to item 1 of argv
              set chatId to item 2 of argv
              tell application "Messages"
                activate
                send msg to chat id chatId
              end tell
            end run
            """
            try runOSA(script: script, args: [body, chatId])
            return
        }

        // If we have a display name for a group, try to target the chat by its name/title
        if let dn = displayName, !dn.isEmpty {
            // 1) Exact match on name or display name
            var script = """
            on run argv
              set msg to item 1 of argv
              set targetName to item 2 of argv
              tell application "Messages"
                activate
                try
                  repeat with c in chats
                    try
                      if name of c is equal to targetName then
                        send msg to c
                        return
                      end if
                    end try
                    try
                      if display name of c is equal to targetName then
                        send msg to c
                        return
                      end if
                    end try
                  end repeat
                end try
              end tell
            end run
            """
            do {
                try runOSA(script: script, args: [body, dn])
                return
            } catch {
                // 2) Case-insensitive/contains match (helps when emoji or suffix differs)
                script = """
                on run argv
                  set msg to item 1 of argv
                  set targetName to item 2 of argv
                  set targetLower to (do shell script "python3 - <<'PY'\nimport sys\nprint(sys.argv[1].lower())\nPY\n" with parameters {targetName})
                  tell application "Messages"
                    activate
                    try
                      repeat with c in chats
                        set nm to ""
                        set dn2 to ""
                        try
                          set nm to name of c
                        end try
                        try
                          set dn2 to display name of c
                        end try
                        set nmLower to ""
                        set dnLower to ""
                        try
                          set nmLower to (do shell script "python3 - <<'PY'\nimport sys\nprint(sys.argv[1].lower())\nPY\n" with parameters {nm})
                        end try
                        try
                          set dnLower to (do shell script "python3 - <<'PY'\nimport sys\nprint(sys.argv[1].lower())\nPY\n" with parameters {dn2})
                        end try
                        if nmLower contains targetLower or dnLower contains targetLower then
                          send msg to c
                          return
                        end if
                      end repeat
                    end try
                  end tell
                end run
                """
                do {
                    try runOSA(script: script, args: [body, dn])
                    return
                } catch {
                    // fall through to participants strategy
                }
            }
        }

        // Fallback: try to find or create a chat with participants and send.
        // Approach:
        // 1) Try to find existing chat via "chat whose participants contains ..." (works on some builds).
        // 2) If not found, try using buddy objects via the first iMessage service and send.
        // 3) As a last fallback, try make new text chat (some macOS builds disallow this -> handle error).
        if participants.isEmpty {
            throw HelperError.sendFailed("non-scriptable chat_id and no participants available")
        }

        let args = ([body] + participants)
        let count = participants.count
        var recipientVars: [String] = []
        var recipientArray: [String] = []
        for i in 0..<count {
            recipientVars.append("set r\(i+1) to item \(i+2) of argv")
            recipientArray.append("r\(i+1)")
        }
        let recipientsList = recipientArray.joined(separator: ", ")

        let script = """
        on run argv
          set msg to item 1 of argv
          \(recipientVars.joined(separator: "\n  "))
          tell application "Messages"
            activate
            -- 1) Try to find an existing chat by participants (best effort)
            try
              set foundChat to missing value
              repeat with c in chats
                try
                  set pIDs to id of participants of c
                on error
                  set pIDs to {}
                end try
                if pIDs is not {} then
                  set matchAll to true
                  repeat with rid in {\(recipientsList)}
                    if pIDs does not contain rid then
                      set matchAll to false
                      exit repeat
                    end if
                  end repeat
                  if matchAll then
                    set foundChat to c
                    exit repeat
                  end if
                end if
              end repeat
              if foundChat is not missing value then
                send msg to foundChat
                return
              end if
            end try

            -- 2) Try sending via buddies on first iMessage service
            try
              set theService to (first service whose service type is iMessage)
              if theService is not missing value then
                if \(count) = 1 then
                  set targetBuddy to buddy \(recipientArray[0]) of theService
                  send msg to targetBuddy
                  return
                else
                  -- Fallback strategy for multi-recipient on builds where group send/new chat is restricted:
                  -- send the message individually to each participant to ensure delivery.
                  repeat with rid in {\(recipientsList)}
                    try
                      set targetBuddy to buddy rid of theService
                      send msg to targetBuddy
                    on error
                      -- ignore failures for individual recipients
                    end try
                  end repeat
                  return
                end if
              end if
            end try

            -- 3) Fallback: attempt to create a new text chat (may fail on some builds)
            try
              set tChat to make new text chat with properties {participants:{\(recipientsList)}}
              send msg to tChat
              return
            on error errMsg number errNum
              error "create text chat failed: " & errMsg
            end try
          end tell
        end run
        """
        try runOSA(script: script, args: args)
    }

    func sendToRecipients(_ recipients: [String], body: String) throws {
        // For each recipient, attempt direct send via "buddy" id. If that fails, create a new chat.
        // We do a single or multi-target chat by opening a new chat with participants if needed.
        if recipients.count == 1 {
            let r = recipients[0]
            let script = """
            on run argv
              set msg to item 1 of argv
              set target to item 2 of argv
              tell application "Messages"
                activate
                send msg to buddy target
              end tell
            end run
            """
            do {
                try runOSA(script: script, args: [body, r])
                return
            } catch {
                // fallback to starting a new chat
            }
        }
        // Fallback: make a new chat with participants (AppleScript UI)
        // Note: Some macOS versions require UI scripting; we try the standard AppleScript first.
        let args = ([body] + recipients)
        let count = recipients.count
        // Build AppleScript that creates a new chat with multiple participants and sends the message
        var recipientVars: [String] = []
        var recipientArray: [String] = []
        for i in 0..<count {
            recipientVars.append("set r\(i+1) to item \(i+2) of argv")
            recipientArray.append("r\(i+1)")
        }
        let recipientsList = recipientArray.joined(separator: ", ")
        let script = """
        on run argv
          set msg to item 1 of argv
          \(recipientVars.joined(separator: "\n  "))
          tell application "Messages"
            activate
            set tChat to make new text chat with properties {participants:{\(recipientsList)}}
            send msg to tChat
          end tell
        end run
        """
        try runOSA(script: script, args: args)
    }

    private func runOSA(script: String, args: [String]) throws {
        // Create temporary script file to avoid quoting pitfalls
        let fm = FileManager.default
        let tmpDir = URL(fileURLWithPath: NSTemporaryDirectory())
        let scriptURL = tmpDir.appendingPathComponent("imhelper-\(UUID().uuidString).applescript")
        try script.write(to: scriptURL, atomically: true, encoding: .utf8)

        // Build /usr/bin/osascript argv: osascript scriptFile arg1 arg2 ...
        var procArgs = [scriptURL.path] + args

        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        task.arguments = procArgs

        let outPipe = Pipe()
        let errPipe = Pipe()
        task.standardOutput = outPipe
        task.standardError = errPipe

        try task.run()
        task.waitUntilExit()

        if task.terminationStatus != 0 {
            let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
            let errStr = String(data: errData, encoding: .utf8) ?? "Unknown AppleScript error"
            throw HelperError.sendFailed(errStr.trimmingCharacters(in: .whitespacesAndNewlines))
        }
    }
}

// MARK: - Main

func readAllStdin() -> Data {
    let stdinFH = FileHandle.standardInput
    return stdinFH.readDataToEndOfFile()
}

func writeJSON<T: Encodable>(_ value: T) {
    let enc = JSONEncoder()
    enc.outputFormatting = [.sortedKeys]
    if let data = try? enc.encode(value) {
        FileHandle.standardOutput.write(data)
    } else {
        let fallback = Data("{\"status\":\"error\",\"error\":\"encode_failed\"}".utf8)
        FileHandle.standardOutput.write(fallback)
    }
}

func writeError(_ message: String) {
    let resp = SendResponse(status: "error", detail: nil, chat_id: nil, to: nil, error: message)
    writeJSON(resp)
}

let inputData = readAllStdin()
let decoder = JSONDecoder()

// Try decode resolve first; if not, try send
if let req = try? decoder.decode(ResolveRequest.self, from: inputData), req.action.lowercased() == "resolve" {
    guard let q = req.query, !q.isEmpty else {
        writeJSON(ResolveResponse(status: "ok", results: []))
        exit(0)
    }
    do {
        let resolver = ChatResolver()
        let results = try resolver.resolve(query: q)
        writeJSON(ResolveResponse(status: "ok", results: results))
    } catch {
        let err = (error as? HelperError) ?? HelperError.invalidInput("resolve_failed")
        writeJSON(ResolveResponse(status: "ok", results: []))
        FileHandle.standardError.write(Data("resolve error: \(err)\n".utf8))
    }
    exit(0)
}

if let req = try? decoder.decode(SendRequest.self, from: inputData), req.action.lowercased() == "send" {
    guard let body = req.body, !body.isEmpty else {
        writeError("missing body")
        exit(0)
    }
    let im = IMessenger()
    do {
        if let chatId = req.chat_id, !chatId.isEmpty {
            // If chatId not scriptable, try resolving participants from DB
            if chatId.range(of: "^[A-Za-z]+;-;.+$", options: .regularExpression) != nil {
                try im.sendToChatIdOrParticipants(chatId, participants: [], body: body)
                writeJSON(SendResponse(status: "sent", detail: "sent to chat_id", chat_id: chatId, to: nil, error: nil))
            } else {
                // Resolve participants for this chatId (match against chat_identifier or guid)
                do {
                    let resolver = ChatResolver()
                    let hits = try resolver.resolve(query: chatId)
                    // Find exact or best match
                    let match = hits.first(where: { $0.chat_id == chatId }) ?? hits.first
                    if let m = match {
                        try im.sendToChatIdOrParticipants(m.chat_id, participants: m.participants, body: body, displayName: m.display_name)
                        writeJSON(SendResponse(status: "sent", detail: "sent via fallback", chat_id: m.chat_id, to: m.participants, error: nil))
                    } else {
                        writeError("chat_id not found in DB")
                    }
                } catch {
                    writeError("resolve participants failed: \(error)")
                }
            }
        } else if let to = req.to, !to.isEmpty {
            try im.sendToRecipients(to, body: body)
            writeJSON(SendResponse(status: "sent", detail: "sent to recipients", chat_id: nil, to: to, error: nil))
        } else {
            writeError("missing chat_id or to[]")
        }
    } catch {
        writeError(String(describing: error))
    }
    exit(0)
}

// Unknown request
writeError("unknown action")
