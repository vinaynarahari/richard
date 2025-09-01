# Richard

A comprehensive macOS AI assistant ecosystem featuring a Swift/SwiftUI menubar app, Python orchestrator, and multiple MCP (Model Context Protocol) servers for external service integrations.

## 🏗️ Architecture

Richard consists of several integrated components:

### 🖥️ **Menubar App** (`apps/menubar/`)
- **Technology**: Swift/SwiftUI
- **Purpose**: Native macOS menubar interface
- **Features**: Chat interface, settings, OAuth flows, connection status
- **Status**: ✅ Fully functional

### 🚀 **Orchestrator Service** (`services/orchestrator/`)
- **Technology**: Python/FastAPI
- **Purpose**: Central API gateway and request routing
- **Port**: 5273
- **Features**: 
  - LLM routing and memory management
  - Voice/STT integration
  - iMessage integration
  - OAuth flows (Gmail, Google Calendar, Notion)
  - Contact management
  - MCP server coordination
- **Status**: ✅ Production ready

### 📱 **Messages Integration** (`mac_messages_mcp/`)
- **Technology**: Python MCP Server
- **Purpose**: Seamless iMessage/SMS integration
- **Features**:
  - Universal message sending (iMessage + SMS/RCS fallback)
  - Message reading and search
  - Contact resolution
  - Group chat support
- **Status**: ✅ Published on PyPI

### 🔗 **MCP Servers** (`mcp-servers/`)
Multiple specialized servers for external service integration:
- **Gmail Server**: Email operations
- **Notion Server**: Database and page management  
- **Google Search Server**: Web search capabilities
- **Playwright Search Server**: Advanced web scraping
- **Status**: ✅ All servers operational

### 🎤 **Voice Integration** (`whisper.cpp/`)
- **Technology**: C++/Python bindings
- **Purpose**: Local speech-to-text processing
- **Status**: ✅ Integrated

## 🚀 Quick Start

### Prerequisites
- macOS 11+
- Python 3.10+
- Xcode (for menubar app)
- `uv` package manager

### 1. Start the Orchestrator
```bash
cd /Users/vinaynarahari/Desktop/Github/richard/services/orchestrator
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 5273
```

### 2. Start MCP Servers
```bash
cd /Users/vinaynarahari/Desktop/Github/richard/mcp-servers
python start-all.py
```

### 3. Build & Run Menubar App
```bash
cd /Users/vinaynarahari/Desktop/Github/richard/apps/menubar
open RichardMenubar.xcodeproj
# Build and run from Xcode
```

### 4. Test the System
```bash
# Health check
curl http://127.0.0.1:5273/health

# Test messages integration (requires Full Disk Access)
# See mac_messages_mcp/README.md for setup
```

## 🔧 Configuration

### Environment Setup
The orchestrator loads configuration from `services/orchestrator/.env`. Key variables:
- OAuth credentials for Gmail, Google Calendar, Notion
- API keys for external services
- Database connection strings

### MCP Server Configuration
MCP servers use `mcp-servers/config.json` for server definitions and routing.

### Full Disk Access (Required for Messages)
Grant Full Disk Access to your terminal/IDE in System Preferences → Security & Privacy → Privacy → Full Disk Access.

## 📦 Components Detail

### Orchestrator Endpoints
- `/llm/*` - LLM routing and chat
- `/memory/*` - Conversation memory
- `/voice/*` - Speech-to-text
- `/imessage/*` - Message operations
- `/oauth/*` - OAuth flows
- `/gmail/*` - Email operations
- `/calendar/*` - Calendar management
- `/notion/*` - Notion integration
- `/search/*` - Web search
- `/contacts/*` - Contact management
- `/mcp/*` - MCP server coordination

### MCP Servers
Each server runs independently and communicates via stdio:
- **Gmail**: Email drafting, sending, reading
- **Notion**: Database queries, page creation/updates
- **Google Search**: Web, image, and news search
- **Playwright**: Advanced web automation and scraping

## 🔒 Security Features

- **OAuth Token Management**: Secure token storage and refresh
- **Database Encryption**: SQLCipher for sensitive data
- **Audit Logging**: Comprehensive operation logging
- **Permission Validation**: Proper macOS permission handling
- **Input Validation**: Robust request validation across all endpoints

## 🧪 Testing

```bash
# Test orchestrator
cd services/orchestrator
python -m pytest

# Test MCP servers
cd mcp-servers
python test_mcp_servers.py

# Test messages integration
cd mac_messages_mcp
python -m pytest tests/
```

## 🛠️ Development

### Adding New MCP Servers
1. Create server directory in `mcp-servers/`
2. Implement MCP protocol in `server.py`
3. Add configuration to `config.json`
4. Update `start-all.py` if needed

### Extending the Orchestrator
1. Add new router in `services/orchestrator/app/routes/`
2. Include router in `main.py`
3. Update dependencies in `pyproject.toml`

## 📄 License

