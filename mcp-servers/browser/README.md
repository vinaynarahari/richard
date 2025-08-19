# Secure Playwright MCP Browser Server

A secure, enterprise-grade browser automation server using Microsoft Playwright MCP with comprehensive security features.

## 🚀 Features

### Browser Automation
- **Web Search**: Multi-engine search (Google, Bing, DuckDuckGo) with browser automation
- **Page Navigation**: Navigate to URLs with safety checks and timeout handling
- **Element Interaction**: Click, type, select, hover, and scroll on page elements
- **Screenshot Capture**: Full page or element-specific screenshots
- **PDF Generation**: Convert pages to PDF documents

### Security Features
- **Authentication & Authorization**: JWT-based auth with role-based permissions
- **Input Validation**: Comprehensive validation and sanitization
- **Rate Limiting**: Configurable limits per operation type
- **Audit Logging**: Complete audit trail of all browser operations
- **Network Security**: Blocked origins, safe URL validation
- **TLS Encryption**: Secure communication with mTLS support

## 📋 Requirements

- **Node.js 18+**: Required for Playwright MCP
- **Python 3.8+**: For security middleware
- **Chromium Browser**: Auto-installed by Playwright

## 🔧 Installation

1. **Install Dependencies**:
   ```bash
   npm install @playwright/mcp@latest playwright
   npx playwright install chromium
   ```

2. **Setup Security**:
   ```bash
   python ../setup_security.py
   ```

3. **Configure Environment**:
   ```bash
   # Copy example configuration
   cp config.json.example config.json
   
   # Set environment variables
   export SECURITY_VAULT_PASSWORD="your_vault_password"
   export JWT_SECRET_KEY="your_jwt_secret"
   ```

## 🛠️ Usage

### Starting the Server

```python
from server import SecureBrowserMCP

browser_server = SecureBrowserMCP()

# Start Playwright MCP server
await browser_server.start_playwright_server()

# Server is now ready for requests
```

### Web Search

```python
# Perform web search
result = await browser_server.search_web(
    query="Python web scraping tutorial",
    max_results=5,
    user_id="authenticated_user"
)
```

### Page Navigation

```python
# Navigate to URL
result = await browser_server.navigate_to_url(
    url="https://www.python.org",
    user_id="authenticated_user"
)
```

### Page Interaction

```python
# Click element
result = await browser_server.interact_with_page(
    action="click",
    target="button#search",
    user_id="authenticated_user"
)

# Type text
result = await browser_server.interact_with_page(
    action="type",
    target="input[name='q']",
    value="search query",
    user_id="authenticated_user"
)
```

## 🔐 Security Configuration

### Authentication

All browser operations require valid JWT authentication:

```python
# Operations require authentication
@require_auth("browser.search")
async def search_web(**kwargs):
    # Implementation
```

### Rate Limiting

Configurable rate limits per operation:
- Search: 30 per minute
- Navigation: 20 per minute  
- Interaction: 50 per minute
- Screenshots: 100 per hour

### Network Security

Blocked domains and URL validation:
```python
blocked_origins = [
    "malware.com",
    "phishing.com",
    "ads.doubleclick.net"
]
```

### Input Validation

Comprehensive input sanitization:
```python
# Query validation
@validate_input(BrowserToolInput)
async def search_web(query: str, **kwargs):
    # Automatically validated and sanitized
```

## 📊 Monitoring & Logging

### Audit Logging

All browser operations are logged:
```
2025-01-01 12:00:00 - AUDIT: browser_search by user123: {
    "query": "python tutorial",
    "results_count": 5,
    "status": "success"
}
```

### Health Monitoring

```python
# Get server status
status = await browser_server.get_server_status()
print(status["status"])  # "running" or "stopped"
```

### Performance Metrics

- Request/response times
- Success/failure rates
- Resource usage
- Security event counts

## 🧪 Testing

Run the test suite:

```bash
python test_browser.py
```

Test coverage includes:
- ✅ Server startup/shutdown
- ✅ Authentication & authorization
- ✅ Input validation
- ✅ Rate limiting
- ✅ Audit logging
- ✅ Network security
- ✅ Browser automation

## ⚙️ Configuration

### Browser Settings

```json
{
  "browser": "chromium",
  "headless": true,
  "viewport": "1280,720",
  "timeout": 30000,
  "max_pages": 5
}
```

### Security Policies

```json
{
  "authentication_required": true,
  "rate_limiting_enabled": true,
  "audit_logging_enabled": true,
  "tls_encryption_enabled": true
}
```

### Network Restrictions

```json
{
  "blocked_origins": ["malware.com", "ads.com"],
  "allowed_origins": [],
  "block_service_workers": true
}
```

## 🔍 Troubleshooting

### Common Issues

1. **Playwright Server Won't Start**:
   ```bash
   npx playwright install chromium
   ```

2. **Authentication Errors**:
   ```bash
   export JWT_SECRET_KEY="your_secret"
   ```

3. **Rate Limit Exceeded**:
   - Check rate limit configuration
   - Implement proper authentication

### Debugging

Enable debug logging:
```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

View traces:
```bash
ls ./traces/  # Playwright execution traces
```

## 📚 API Reference

### Methods

| Method | Permission | Description |
|--------|------------|-------------|
| `search_web()` | `browser.search` | Perform web search |
| `navigate_to_url()` | `browser.navigate` | Navigate to URL |
| `interact_with_page()` | `browser.interact` | Interact with elements |
| `get_server_status()` | `browser.admin` | Get server status |

### Parameters

| Parameter | Type | Description | Validation |
|-----------|------|-------------|------------|
| `query` | string | Search query | Max 1000 chars |
| `url` | string | Target URL | Valid HTTP/HTTPS |
| `action` | enum | Interaction type | click, type, select, etc. |
| `max_results` | integer | Result limit | 1-50 |

## 🚀 Production Deployment

### Security Checklist

- [ ] TLS certificates installed
- [ ] Vault password configured
- [ ] Rate limiting enabled
- [ ] Audit logging configured
- [ ] Firewall rules applied
- [ ] Monitoring alerts setup

### Performance Optimization

- Use headless browser mode
- Configure appropriate timeouts
- Limit concurrent browser instances
- Enable request/response compression
- Monitor resource usage

## 📞 Support

For issues or questions:
- **Security Issues**: security@example.com
- **Technical Support**: support@example.com  
- **Documentation**: See `SECURITY.md` for detailed security information

## 📄 License

This secure Playwright MCP implementation is part of the Richard application suite and follows enterprise security standards.