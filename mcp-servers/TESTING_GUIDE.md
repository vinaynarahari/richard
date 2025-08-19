# MCP Servers Testing Guide for Richard

## ✅ Status: All Servers Working

All 4 MCP servers are now functional and ready for integration with Richard:

- **Gmail MCP Server** 🟢 Running
- **Notion MCP Server** 🟢 Running  
- **Google Search MCP Server** 🟢 Running
- **Playwright Search MCP Server** 🟢 Running

## 🚀 Quick Start

1. **Start all servers:**
   ```bash
   cd /Users/vinaynarahari/Desktop/Github/richard/mcp-servers
   python start-all.py
   ```

2. **Verify servers are running:**
   ```bash
   python test_mcp_servers.py
   ```

## 🔧 Server Capabilities

### Gmail MCP Server
- **Tools:** Email management, drafting, sending
- **Security:** Authentication, rate limiting, audit logging
- **Command:** `python gmail/server.py`

### Notion MCP Server  
- **Tools:** Database queries, page creation, content management
- **Security:** Token validation, permission management
- **Command:** `python notion/server.py`

### Google Search MCP Server
- **Tools:** Web search, result filtering, content extraction
- **Security:** Query validation, rate limiting
- **Command:** `python google-search/server.py`

### Playwright Search MCP Server
- **Tools:** Browser automation, web scraping, screenshot capture
- **Features:** Multi-browser support (Chrome, Firefox, WebKit), headless mode, trace recording
- **Security:** Origin blocking, service worker blocking
- **Command:** `node cli.js --headless --browser chromium`

## 🔗 Richard Integration

### Option 1: MCP Client Integration
Use the provided configuration file `richard_mcp_config.json` to connect Richard to these servers via MCP protocol.

### Option 2: Direct API Integration  
The servers can also be accessed directly via their stdio interface for custom integration.

## 🧪 Testing Commands

Test basic functionality:
```bash
# Test all servers
python test_mcp_servers.py

# Start servers individually for debugging
PYTHONPATH=. python gmail/server.py
PYTHONPATH=. python notion/server.py  
PYTHONPATH=. python google-search/server.py
cd playwright-search && node cli.js --help
```

## 🔒 Security Features

All servers include:
- Authentication and authorization
- Rate limiting
- Input validation  
- Audit logging
- Secure credential storage (when vault password is configured)

## 📝 Next Steps

1. **Configure Richard** to use the MCP servers via the provided config
2. **Test specific workflows** like:
   - Gmail: Draft and send emails
   - Notion: Query databases and create pages
   - Google Search: Perform searches and extract results
   - Playwright: Automate browser tasks and capture screenshots
3. **Monitor logs** in the `logs/` directory for debugging

## 🐛 Troubleshooting

- **Security warnings about vault password:** This is normal when no vault password is configured. The servers will work in basic security mode.
- **Import errors:** Ensure `PYTHONPATH` includes the mcp-servers directory
- **Port conflicts:** Default ports are used, ensure they're available
- **Playwright issues:** Ensure Node.js dependencies are installed with `npm install`

---

**Status:** ✅ Ready for production use with Richard!