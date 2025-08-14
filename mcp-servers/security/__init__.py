"""
Security module for MCP servers.
Provides comprehensive security features including authentication, authorization,
input validation, encryption, audit logging, and secure communication.
"""

from .auth import SecurityConfig, TokenManager, RateLimiter, PermissionManager, AuditLogger
from .validation import SecurityValidator, ValidationError, DataType, GmailToolInput, NotionToolInput, SearchToolInput
from .crypto import SecureCrypto, SecureVault, SecureSession
from .middleware import SecurityMiddleware, require_auth, validate_input, rate_limit
from .tls_config import TLSConfig

__version__ = "1.0.0"
__all__ = [
    "SecurityConfig",
    "TokenManager", 
    "RateLimiter",
    "PermissionManager",
    "AuditLogger",
    "SecurityValidator",
    "ValidationError",
    "DataType",
    "GmailToolInput",
    "NotionToolInput", 
    "SearchToolInput",
    "SecureCrypto",
    "SecureVault",
    "SecureSession",
    "SecurityMiddleware",
    "require_auth",
    "validate_input",
    "rate_limit",
    "TLSConfig"
]

# Initialize security components
security_middleware = SecurityMiddleware()

def init_security(config_path: str = None) -> SecurityMiddleware:
    """Initialize security middleware with optional config path."""
    global security_middleware
    security_middleware = SecurityMiddleware(config_path)
    return security_middleware

def get_security() -> SecurityMiddleware:
    """Get the global security middleware instance."""
    return security_middleware