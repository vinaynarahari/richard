"""
Authentication and authorization middleware for MCP servers.
Implements industry-standard security practices including JWT tokens,
role-based access control, and secure session management.
"""

import os
import jwt
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import logging
from functools import wraps

logger = logging.getLogger(__name__)

class SecurityConfig:
    """Security configuration with secure defaults."""
    
    def __init__(self):
        # JWT Configuration
        self.JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY') or self._generate_jwt_secret()
        self.JWT_ALGORITHM = 'HS256'
        self.JWT_EXPIRATION_DELTA = timedelta(hours=1)
        self.JWT_REFRESH_DELTA = timedelta(days=7)
        
        # Rate Limiting
        self.RATE_LIMIT_REQUESTS = int(os.getenv('RATE_LIMIT_REQUESTS', '100'))
        self.RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', '3600'))  # 1 hour
        
        # Session Security
        self.SESSION_COOKIE_SECURE = True
        self.SESSION_COOKIE_HTTPONLY = True
        self.SESSION_COOKIE_SAMESITE = 'Strict'
        
        # Encryption
        self.ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY') or self._generate_encryption_key()
        
        # API Keys
        self.API_KEY_LENGTH = 32
        self.API_KEY_PREFIX = 'mcp_'
        
        # Audit
        self.AUDIT_LOG_ENABLED = os.getenv('AUDIT_LOG_ENABLED', 'true').lower() == 'true'
        self.AUDIT_LOG_PATH = os.getenv('AUDIT_LOG_PATH', './logs/audit.log')
        
    def _generate_jwt_secret(self) -> str:
        """Generate a cryptographically secure JWT secret."""
        return secrets.token_urlsafe(64)
    
    def _generate_encryption_key(self) -> str:
        """Generate a Fernet encryption key."""
        return Fernet.generate_key().decode()

class TokenManager:
    """Secure JWT token management."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.blacklisted_tokens: Set[str] = set()
        
    def create_access_token(self, user_id: str, permissions: List[str], 
                           additional_claims: Optional[Dict] = None) -> str:
        """Create a JWT access token with proper claims."""
        now = datetime.now(timezone.utc)
        payload = {
            'sub': user_id,
            'iat': now.timestamp(),
            'exp': (now + self.config.JWT_EXPIRATION_DELTA).timestamp(),
            'jti': secrets.token_urlsafe(16),  # JWT ID for blacklisting
            'permissions': permissions,
            'type': 'access'
        }
        
        if additional_claims:
            payload.update(additional_claims)
            
        return jwt.encode(payload, self.config.JWT_SECRET_KEY, algorithm=self.config.JWT_ALGORITHM)
    
    def create_refresh_token(self, user_id: str) -> str:
        """Create a refresh token."""
        now = datetime.now(timezone.utc)
        payload = {
            'sub': user_id,
            'iat': now.timestamp(),
            'exp': (now + self.config.JWT_REFRESH_DELTA).timestamp(),
            'jti': secrets.token_urlsafe(16),
            'type': 'refresh'
        }
        
        return jwt.encode(payload, self.config.JWT_SECRET_KEY, algorithm=self.config.JWT_ALGORITHM)
    
    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify and decode a JWT token."""
        try:
            if token in self.blacklisted_tokens:
                logger.warning(f"Attempted to use blacklisted token")
                return None
                
            payload = jwt.decode(
                token, 
                self.config.JWT_SECRET_KEY, 
                algorithms=[self.config.JWT_ALGORITHM]
            )
            
            # Check if token is expired
            if payload['exp'] < time.time():
                logger.warning(f"Expired token attempted for user {payload.get('sub')}")
                return None
                
            return payload
            
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
    
    def blacklist_token(self, token: str):
        """Add token to blacklist (for logout)."""
        try:
            payload = jwt.decode(
                token, 
                self.config.JWT_SECRET_KEY, 
                algorithms=[self.config.JWT_ALGORITHM],
                options={"verify_exp": False}  # Allow blacklisting expired tokens
            )
            jti = payload.get('jti')
            if jti:
                self.blacklisted_tokens.add(jti)
                logger.info(f"Token blacklisted for user {payload.get('sub')}")
        except jwt.InvalidTokenError:
            pass  # Invalid tokens don't need blacklisting

class RateLimiter:
    """Token bucket rate limiter for DDoS protection."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.buckets: Dict[str, Dict] = {}
        
    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed based on rate limits."""
        now = time.time()
        
        if identifier not in self.buckets:
            self.buckets[identifier] = {
                'tokens': self.config.RATE_LIMIT_REQUESTS,
                'last_update': now
            }
            return True
        
        bucket = self.buckets[identifier]
        
        # Add tokens based on time elapsed
        time_passed = now - bucket['last_update']
        tokens_to_add = time_passed * (self.config.RATE_LIMIT_REQUESTS / self.config.RATE_LIMIT_WINDOW)
        
        bucket['tokens'] = min(
            self.config.RATE_LIMIT_REQUESTS, 
            bucket['tokens'] + tokens_to_add
        )
        bucket['last_update'] = now
        
        if bucket['tokens'] >= 1:
            bucket['tokens'] -= 1
            return True
        else:
            logger.warning(f"Rate limit exceeded for {identifier}")
            return False

class PermissionManager:
    """Role-based access control (RBAC) system."""
    
    # Define permissions for different MCP operations
    PERMISSIONS = {
        'gmail.read': 'Read Gmail messages',
        'gmail.send': 'Send Gmail messages', 
        'gmail.draft': 'Create Gmail drafts',
        'notion.read': 'Read Notion content',
        'notion.write': 'Write Notion content',
        'notion.search': 'Search Notion workspace',
        'search.web': 'Perform web searches',
        'search.image': 'Perform image searches',
        'search.news': 'Perform news searches',
        'admin.all': 'Full administrative access'
    }
    
    ROLES = {
        'readonly': ['gmail.read', 'notion.read', 'search.web', 'search.image', 'search.news'],
        'user': ['gmail.read', 'gmail.send', 'gmail.draft', 'notion.read', 'notion.write', 
                'notion.search', 'search.web', 'search.image', 'search.news'],
        'admin': list(PERMISSIONS.keys())
    }
    
    @classmethod
    def get_permissions_for_role(cls, role: str) -> List[str]:
        """Get permissions for a role."""
        return cls.ROLES.get(role, [])
    
    @classmethod
    def check_permission(cls, user_permissions: List[str], required_permission: str) -> bool:
        """Check if user has required permission."""
        return required_permission in user_permissions or 'admin.all' in user_permissions

class AuditLogger:
    """Security audit logging."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        if config.AUDIT_LOG_ENABLED:
            self._setup_audit_logger()
    
    def _setup_audit_logger(self):
        """Set up audit logging."""
        os.makedirs(os.path.dirname(self.config.AUDIT_LOG_PATH), exist_ok=True)
        
        self.audit_logger = logging.getLogger('audit')
        self.audit_logger.setLevel(logging.INFO)
        
        handler = logging.FileHandler(self.config.AUDIT_LOG_PATH)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.audit_logger.addHandler(handler)
    
    def log_authentication(self, user_id: str, success: bool, ip_address: str = None):
        """Log authentication attempts."""
        if not self.config.AUDIT_LOG_ENABLED:
            return
            
        status = "SUCCESS" if success else "FAILED"
        self.audit_logger.info(
            f"AUTH - {status} - User: {user_id} - IP: {ip_address or 'unknown'}"
        )
    
    def log_api_call(self, user_id: str, tool_name: str, success: bool, 
                     ip_address: str = None, error_msg: str = None):
        """Log API calls."""
        if not self.config.AUDIT_LOG_ENABLED:
            return
            
        status = "SUCCESS" if success else "FAILED" 
        error_info = f" - Error: {error_msg}" if error_msg else ""
        self.audit_logger.info(
            f"API - {status} - User: {user_id} - Tool: {tool_name} - IP: {ip_address or 'unknown'}{error_info}"
        )
    
    def log_security_event(self, event_type: str, details: str, severity: str = "INFO"):
        """Log security events."""
        if not self.config.AUDIT_LOG_ENABLED:
            return
            
        self.audit_logger.log(
            getattr(logging, severity.upper(), logging.INFO),
            f"SECURITY - {event_type} - {details}"
        )

class SecureCredentialManager:
    """Secure credential storage and management."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.fernet = Fernet(config.ENCRYPTION_KEY.encode())
    
    def encrypt_credential(self, credential: str) -> str:
        """Encrypt a credential."""
        return self.fernet.encrypt(credential.encode()).decode()
    
    def decrypt_credential(self, encrypted_credential: str) -> str:
        """Decrypt a credential."""
        return self.fernet.decrypt(encrypted_credential.encode()).decode()
    
    def hash_api_key(self, api_key: str) -> str:
        """Create a secure hash of an API key."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def generate_api_key(self) -> str:
        """Generate a secure API key."""
        key = secrets.token_urlsafe(self.config.API_KEY_LENGTH)
        return f"{self.config.API_KEY_PREFIX}{key}"

# Security decorators
def require_auth(permission: Optional[str] = None):
    """Decorator to require authentication and optionally specific permissions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # This would be implemented in the actual MCP server context
            # For now, this is a template for how it would work
            pass
        return wrapper
    return decorator

def rate_limit(identifier_func=lambda *args, **kwargs: "default"):
    """Decorator to apply rate limiting."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Rate limiting logic would be implemented here
            pass
        return wrapper
    return decorator