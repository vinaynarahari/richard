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
    // For new action send_by_display_name
    let display_name: String?
    // For new action send_by_contact_name
    let contact: String?
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
        // Strict mode: send to chat id if scriptable; else try display name; else try participants as buddies (no new chat creation).
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
        if let dn = displayName, !dn.isEmpty {
            do {
                try sendByDisplayName(dn, body: body)
                return
            } catch { }
        }
        if !participants.isEmpty {
            try sendToRecipients(participants, body: body)
            return
        }
        throw HelperError.sendFailed("non-scriptable chat_id and no participants available")
    }

    func sendToRecipients(_ recipients: [String], body: String) throws {
        // Strict mode: send only to existing buddy objects; no new chat creation.
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
            try runOSA(script: script, args: [body, r])
            return
        }
        // Multiple recipients: send individually to each existing buddy
        for r in recipients {
            let script = """
            on run argv
              set msg to item 1 of argv
              set target to item 2 of argv
              tell application "Messages"
                activate
                try
                  send msg to buddy target
                on error
                  -- ignore if buddy not found
                end try
              end tell
            end run
            """
            _ = try? runOSA(script: script, args: [body, r])
        }
    }

    // Send directly to a chat by its display name (exact or fuzzy). No participants fallback here.
    func sendByDisplayName(_ displayName: String, body: String) throws {
        let script = """
        on run argv
          set msg to item 1 of argv
          set targetName to (item 2 of argv) as text
          tell application "Messages"
            activate
            -- Exact match on 'name' only
            try
              repeat with c in chats
                try
                  if (name of c as text) is equal to targetName then
                    send msg to c
                    return
                  end if
                end try
              end repeat
            end try

            -- Fuzzy contains on 'name'
            try
              repeat with c in chats
                try
                  set nm to (name of c as text)
                  if nm contains targetName then
                    send msg to c
                    return
                  end if
                end try
              end repeat
            end try
          end tell
        end run
        """
        try runOSA(script: script, args: [body, displayName])
    }

    // Search buddies by display name (case-insensitive contains). Returns list of handles (ids).
    func findBuddiesByName(_ name: String) throws -> [String] {
        // Return candidates as "handleId|displayName" per line so the API can offer fuzzy options.
        // Avoid AppleScript 'contains' on lists and avoid reserved word parsing by using equality in loops.
        let script = """
        on toLowerTxt(s)
          try
            return (do shell script "python3 - <<'PY'\nimport sys\nprint(sys.argv[1].lower())\nPY\n" with parameters {s})
          on error
            return s
          end try
        end toLowerTxt

        on newline()
          return (ASCII character 10)
        end newline

        on isInList(theItem, theList)
          repeat with x in theList
            if (x as text) is equal to (theItem as text) then return true
          end repeat
          return false
        end isInList

        on uniqAppend(listText, itemText)
          if listText is "" then return itemText
          set nl to (ASCII character 10)
          set AppleScript's text item delimiters to nl
          set itemsList to every text item of listText
          set AppleScript's text item delimiters to ""
          if my isInList(itemText, itemsList) then return listText
          return listText & nl & itemText
        end uniqAppend

        on ensureList(v)
          try
            set _c to (count of v)
            return v
          on error
            if v is missing value then return {}
            return {v}
          end try
        end ensureList

        on listContains(theList, theItem)
          repeat with x in theList
            if (x as text) is equal to (theItem as text) then return true
          end repeat
          return false
        end listContains

        on run argv
          set targetName to item 1 of argv
          set targetLower to toLowerTxt(targetName)
          set outText to ""
          tell application "Messages"
            try
              repeat with c in chats
                set partNames to {}
                set partIds to {}
                try
                  set partNames to my ensureList(name of participants of c)
                on error
                  set partNames to {}
                end try
                try
                  set partIds to my ensureList(id of participants of c)
                on error
                  set partIds to {}
                end try

                set idx to 1
                repeat with pn in partNames
                  set nm to ""
                  try
                    set nm to (pn as text)
                  end try
                  set nmLower to toLowerTxt(nm)

                  -- safe substring test without list 'contains'
                  set matchFound to false
                  set tnLen to (length of targetLower)
                  if tnLen is 0 then
                    set matchFound to false
                  else
                    try
                      set nmLen to (length of nmLower)
                      set i to 1
                      repeat while i <= (nmLen - tnLen + 1)
                        if (text i thru (i + tnLen - 1) of nmLower) is equal to targetLower then
                          set matchFound to true
                          exit repeat
                        end if
                        set i to i + 1
                      end repeat
                    end try
                  end if

                  if matchFound then
                    set hid to ""
                    try
                      set hid to (item idx of partIds) as text
                    end try
                    if hid is not "" then
                      set line to hid & "|" & nm
                      set outText to my uniqAppend(outText, line)
                    end if
                  end if
                  set idx to idx + 1
                end repeat
              end repeat
            end try
          end tell
          return outText
        end run
        """
        let tmp = try runOSACollect(script: script, args: [name])
        let trimmed = tmp.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return []
        }
        // parse "handle|name" lines, but API expects handle ids list for unique, or candidates when multiple
        return trimmed.split(whereSeparator: \.isNewline).map { String($0.split(separator: "|", maxSplits: 1, omittingEmptySubsequences: false).first ?? Substring("")) }
    }

    // Send to a buddy id (single recipient)
    func sendToBuddyId(_ buddyId: String, body: String) throws {
        // Avoid buddy references entirely: find an existing chat whose participants include this handle id and send to that chat.
        // If not found, attempt to create a new text chat with this participant.
        let script = """
        on run argv
          set msg to item 1 of argv
          set hid to item 2 of argv
          tell application "Messages"
            activate
            -- 1) Try to find an existing chat containing this handle id
            try
              repeat with c in chats
                set pIDs to {}
                try
                  set pIDs to (id of participants of c)
                end try
                if pIDs contains hid then
                  send msg to c
                  return
                end if
              end repeat
            end try
            -- 2) Fallback: try to make a new text chat with this participant
            try
              set tChat to make new text chat with properties {participants:{hid}}
              send msg to tChat
              return
            on error errMsg number errNum
              error "no_chat_for_handle:" & errMsg
            end try
          end tell
        end run
        """
        try runOSA(script: script, args: [body, buddyId])
    }

    // Convenience to capture stdout string from AppleScript run
    func runOSACollect(script: String, args: [String]) throws -> String {
        // Create temporary script file to avoid quoting pitfalls
        let tmpDir = URL(fileURLWithPath: NSTemporaryDirectory())
        let scriptURL = tmpDir.appendingPathComponent("imhelper-\(UUID().uuidString).applescript")
        try script.write(to: scriptURL, atomically: true, encoding: .utf8)

        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        task.arguments = [scriptURL.path] + args

        let outPipe = Pipe()
        let errPipe = Pipe()
        task.standardOutput = outPipe
        task.standardError = errPipe

        try task.run()
        task.waitUntilExit()

        let outData = outPipe.fileHandleForReading.readDataToEndOfFile()
        let outStr = String(data: outData, encoding: .utf8) ?? ""
        if task.terminationStatus != 0 {
            let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
            let errStr = String(data: errData, encoding: .utf8) ?? "Unknown AppleScript error"
            throw HelperError.sendFailed(errStr.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return outStr
    }

    func runOSA(script: String, args: [String]) throws {
        // Create temporary script file to avoid quoting pitfalls
        let tmpDir = URL(fileURLWithPath: NSTemporaryDirectory())
        let scriptURL = tmpDir.appendingPathComponent("imhelper-\(UUID().uuidString).applescript")
        try script.write(to: scriptURL, atomically: true, encoding: .utf8)

        // Build /usr/bin/osascript argv: osascript scriptFile arg1 arg2 ...
        let procArgs = [scriptURL.path] + args

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

// Fuzzy resolver via AppleScript over Messages: matches chat name/display name or participant names
func resolveViaAppleScript(_ query: String) throws -> [ResolveResult] {
    let script = """
    on toLowerTxt(s)
      try
        return (do shell script "python3 - <<'PY'\nimport sys\nprint(sys.argv[1].lower())\nPY\n" with parameters {s})
      on error
        return s
      end try
    end toLowerTxt

    on ensureList(v)
      try
        set _c to (count of v)
        return v
      on error
        if v is missing value then return {}
        return {v}
      end try
    end ensureList

    on joinCSV(lst)
      set txt to ""
      repeat with x in lst
        set s to (x as text)
        if txt is "" then
          set txt to s
        else
          set txt to txt & "," & s
        end if
      end repeat
      return txt
    end joinCSV

    on run argv
      set targetName to item 1 of argv
      set targetLower to toLowerTxt(targetName)
      set outText to ""
      tell application "Messages"
        try
          repeat with c in chats
            set cId to ""
            try
              set cId to (id of c) as text
            end try
            set cName to ""
            set cDN to ""
            try
              set cName to (name of c) as text
            end try
            try
              set cDN to (display name of c) as text
            end try
            set pNames to my ensureList(name of participants of c)
            set pIds to my ensureList(id of participants of c)

            set match to false
            set nmLower to toLowerTxt(cName)
            set dnLower to toLowerTxt(cDN)
            if (nmLower contains targetLower) or (dnLower contains targetLower) then
              set match to true
            else
              repeat with pn in pNames
                set pnLower to toLowerTxt(pn as text)
                if pnLower contains targetLower then
                  set match to true
                  exit repeat
                end if
              end repeat
            end if

            if match then
              set pCSV to my joinCSV(pIds)
              set disp to cName
              if disp is "" then set disp to cDN
              if outText is "" then
                set outText to cId & "|" & disp & "|" & pCSV
              else
                set outText to outText & (ASCII character 10) & cId & "|" & disp & "|" & pCSV
              end if
            end if
          end repeat
        end try
      end tell
      return outText
    end run
    """
    let tmp = try IMessenger().runOSACollect(script: script, args: [query])
    let trimmed = tmp.trimmingCharacters(in: CharacterSet.whitespacesAndNewlines)
    if trimmed.isEmpty { return [] }
    var results: [ResolveResult] = []
    for line in trimmed.split(whereSeparator: { $0.isNewline }) {
      let parts = String(line).split(separator: "|", maxSplits: 2, omittingEmptySubsequences: false)
      let chatId = parts.count > 0 ? String(parts[0]) : ""
      let disp = parts.count > 1 ? String(parts[1]) : nil
      let pCSV = parts.count > 2 ? String(parts[2]) : ""
      let participants = pCSV.isEmpty ? [] : pCSV.split(separator: ",").map { String($0) }
      results.append(ResolveResult(chat_id: chatId, display_name: disp, participants: participants, chat_guid: nil, chat_identifier: nil))
    }
    return results
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

// New: AppleScript-based resolver for names/participants
if let req = try? decoder.decode(ResolveRequest.self, from: inputData), req.action.lowercased() == "resolve_as" {
    guard let q = req.query, !q.isEmpty else {
        writeJSON(ResolveResponse(status: "ok", results: []))
        exit(0)
    }
    do {
        let results = try resolveViaAppleScript(q)
        writeJSON(ResolveResponse(status: "ok", results: results))
    } catch {
        writeJSON(ResolveResponse(status: "ok", results: []))
    }
    exit(0)
}

if let req = try? decoder.decode(SendRequest.self, from: inputData), req.action.lowercased() == "send_by_display_name" {
    guard let body = req.body, !body.isEmpty else {
        writeError("missing body")
        exit(0)
    }
    guard let dn = req.display_name, !dn.isEmpty else {
        writeError("missing display_name")
        exit(0)
    }
    let im = IMessenger()
    do {
        try im.sendByDisplayName(dn, body: body)
        writeJSON(SendResponse(status: "sent", detail: "sent to display_name", chat_id: nil, to: nil, error: nil))
    } catch {
        writeError(String(describing: error))
    }
    exit(0)
}

if let req = try? decoder.decode(SendRequest.self, from: inputData), req.action.lowercased() == "send_by_contact_name" {
    // Case-insensitive contains search on buddy display names. If multiple, return 409 with candidates.
    guard let body = req.body, !body.isEmpty else {
        writeError("missing body")
        exit(0)
    }
    guard let contact = req.contact, !contact.isEmpty else {
        writeError("missing contact")
        exit(0)
    }
    let im = IMessenger()
    do {
        let candidates = try im.findBuddiesByName(contact)
        if candidates.isEmpty {
            writeError("no_match")
            exit(0)
        }
        if candidates.count > 1 {
            // Multiple matches: return candidates to let API choose a preferred handle
                let resp = SendResponse(status: "error", detail: "multiple_matches", chat_id: nil, to: candidates, error: "multiple_matches")
                writeJSON(resp)
                exit(0)
        }
        // Use participants->chat path to avoid buddy AppleScript object path entirely
        try im.sendToBuddyId(candidates[0], body: body)
        writeJSON(SendResponse(status: "sent", detail: "sent to contact", chat_id: nil, to: [candidates[0]], error: nil))
    } catch {
        writeError(String(describing: error))
    }
    exit(0)
}

if let req = try? decoder.decode(SendRequest.self, from: inputData), req.action.lowercased() == "lookup_contact_handles" {
    // Lookup phone numbers and emails from Contacts for a given display name (case-insensitive contains)
    guard let contact = req.contact, !contact.isEmpty else {
        writeError("missing contact")
        exit(0)
    }
    let script = """
    on newline()
      return (ASCII character 10)
    end newline

    on joinCSV(lst)
      set txt to ""
      repeat with x in lst
        set s to (x as text)
        if txt is "" then
          set txt to s
        else
          set txt to txt & "," & s
        end if
      end repeat
      return txt
    end joinCSV

    on toLowerTxt(s)
      try
        return (do shell script "python3 - <<'PY'\nimport sys\nprint(sys.argv[1].lower())\nPY\n" with parameters {s})
      on error
        return s
      end try
    end toLowerTxt

    on run argv
      set targetName to item 1 of argv
      set targetLower to toLowerTxt(targetName)
      set handles to {}
      tell application "Contacts"
        try
          repeat with p in people
            set fullName to ""
            try
              set fullName to (name of p) as text
            end try
            set nmLower to toLowerTxt(fullName)
            if nmLower contains targetLower then
              try
                repeat with ph in phones of p
                  try
                    set end of handles to (value of ph) as text
                  end try
                end repeat
              end try
              try
                repeat with em in emails of p
                  try
                    set end of handles to (value of em) as text
                  end try
                end repeat
              end try
            end if
          end repeat
        end try
      end tell
      if (count of handles) is 0 then
        return ""
      end if
      set outText to my joinCSV(handles)
      return outText
    end run
    """
    do {
        let im = IMessenger()
        let out = try im.runOSACollect(script: script, args: [contact])
        let trimmed = out.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            // no matches
            let resp = ["status": "ok", "handles": []] as [String : Any]
            let json = try JSONSerialization.data(withJSONObject: resp, options: [])
            FileHandle.standardOutput.write(json)
            exit(0)
        }
        let parts = trimmed.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
        let resp = ["status": "ok", "handles": parts] as [String : Any]
        let json = try JSONSerialization.data(withJSONObject: resp, options: [])
        FileHandle.standardOutput.write(json)
    } catch {
        writeError(String(describing: error))
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
            // First, try sending directly to chat id regardless of pattern
            do {
                let script = """
                on run argv
                  set msg to item 1 of argv
                  set cid to item 2 of argv
                  tell application "Messages"
                    activate
                    send msg to chat id cid
                  end tell
                end run
                """
                try im.runOSA(script: script, args: [body, chatId])
                writeJSON(SendResponse(status: "sent", detail: "sent to chat_id", chat_id: chatId, to: nil, error: nil))
                exit(0)
            } catch {
                // If direct chat id fails, and id is scriptable, try standard path
                if chatId.range(of: "^[A-Za-z]+;-;.+$", options: .regularExpression) != nil {
                    try im.sendToChatIdOrParticipants(chatId, participants: [], body: body)
                    writeJSON(SendResponse(status: "sent", detail: "sent to chat_id", chat_id: chatId, to: nil, error: nil))
                    exit(0)
                }
                // Else resolve participants for this chatId using DB and fall back
                do {
                    let resolver = ChatResolver()
                    let hits = try resolver.resolve(query: chatId)
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
