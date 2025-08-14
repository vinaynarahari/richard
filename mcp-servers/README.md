# MCP Servers for Richard

This directory contains Model Context Protocol (MCP) servers that provide external service integrations for the Richard application.

## Available Servers

### 1. Gmail Server (`gmail/`)
Provides Gmail API integration for email operations.

**Tools:**
- `gmail_send_email`: Send emails via Gmail
- `gmail_create_draft`: Create draft emails
- `gmail_list_messages`: List recent messages
- `gmail_get_message`: Get details of a specific message

**Authentication:** Uses OAuth tokens managed by the main orchestrator service.

### 2. Notion Server (`notion/`)
Provides Notion API integration for database and page operations.

**Tools:**
- `notion_query_database`: Query Notion databases
- `notion_create_page`: Create new pages in databases
- `notion_update_page`: Update existing pages
- `notion_get_page`: Get page details
- `notion_get_database`: Get database schema
- `notion_search`: Search across workspace

**Authentication:** Requires `NOTION_TOKEN` environment variable.

### 3. Google Search Server (`google-search/`)
Provides Google Custom Search API integration.

**Tools:**
- `google_web_search`: Perform web searches
- `google_image_search`: Search for images
- `google_news_search`: Search for news articles

**Authentication:** Requires `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID` environment variables.

## Setup

1. **Install dependencies:**
   ```bash
   python setup.py
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Configure your MCP client:**
   Use the `config.json` file to configure your MCP client to connect to these servers.

## Environment Variables

### Required for each server:

**Notion Server:**
- `NOTION_TOKEN`: Your Notion integration token

**Google Search Server:**
- `GOOGLE_SEARCH_API_KEY`: Your Google Custom Search API key
- `GOOGLE_SEARCH_ENGINE_ID`: Your Custom Search Engine ID

**Gmail Server:**
OAuth tokens are automatically managed through the main application's OAuth flow.

## Usage Examples

### Gmail
```python
# Send an email
await gmail_send_email({
    "account": "user@example.com",
    "to": ["recipient@example.com"],
    "subject": "Hello from MCP",
    "body": "This email was sent via the Gmail MCP server!"
})
```

### Notion
```python
# Query a database
await notion_query_database({
    "database_id": "your_database_id",
    "filter": {
        "property": "Status",
        "select": {"equals": "In Progress"}
    }
})
```

### Google Search
```python
# Search the web
await google_web_search({
    "query": "MCP protocol documentation",
    "num_results": 5
})
```

## Testing

Each server can be tested independently:

```bash
# Test Gmail server
python -m gmail.server

# Test Notion server
python -m notion.server

# Test Google Search server
python -m google-search.server
```

## Integration with Main Application

These MCP servers are designed to replace the direct API calls in the main Richard application. The orchestrator service can connect to these servers via the MCP protocol for cleaner separation of concerns and better maintainability.

## Security Notes

- All servers use environment variables for sensitive configuration
- OAuth tokens for Gmail are managed through the existing secure token store
- Servers run in isolated processes communicating via stdio
- No sensitive data is logged or exposed in server responses