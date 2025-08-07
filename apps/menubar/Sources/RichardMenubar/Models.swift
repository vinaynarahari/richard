import Foundation

struct OAuthStatus: Codable, Identifiable {
    var id: String { provider }
    let provider: String
    let connected: Bool
    let mode: String?
    let accounts: [String]?
}

struct CalendarCreateRequest: Codable {
    let account: String?
    let summary: String
    let start_iso: String
    let end_iso: String
    let timezone: String
    let attendees: [String]
    let description: String?
    let location: String?
    let confirm: Bool
}

struct CalendarCreateResponse: Codable {
    let event_id: String?
    let htmlLink: String?
    let status: String?
    let provider: String?
}

struct GmailDraftRequest: Codable {
    let account: String?
    let to: [String]
    let subject: String
    let body_markdown: String
}

struct GmailDraftResponse: Codable {
    let draft_id: String?
    let status: String?
    let provider: String?
}

struct NotionCreateRequest: Codable {
    let database_id: String
    let parent_hint: String? // e.g. "page"
    let title: String
    let properties: [String: String]?
    let content_markdown: String?
}

struct NotionCreateResponse: Codable {
    let page_id: String?
    let status: String?
    let provider: String?
}
