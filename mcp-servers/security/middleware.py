"""
Security middleware for MCP servers.
Integrates authentication, authorization, validation, rate limiting, and audit logging.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from functools import wraps
import json
import os
from datetime import datetime

from .auth import SecurityConfig, TokenManager, RateLimiter, PermissionManager, AuditLogger
from .validation import SecurityValidator, ValidationError, DataType
from .crypto import SecureVault, SecureSession

logger = logging.getLogger(__name__)

class SecurityMiddleware:
    """Centralized security middleware for MCP servers."""
    
    def __init__(self, config_path: Optional[str] = None):
        # Initialize security components
        self.config = SecurityConfig()
        self.token_manager = TokenManager(self.config)
        self.rate_limiter = RateLimiter(self.config)
        self.audit_logger = AuditLogger(self.config)
        self.session_manager = SecureSession()
        
        # Initialize secure vault if vault path is provided
        vault_path = os.getenv('SECURITY_VAULT_PATH', './security/vault.enc')
        vault_password = os.getenv('SECURITY_VAULT_PASSWORD')
        
        if vault_password:
            try:
                self.vault = SecureVault(vault_path, vault_password)
                logger.info("Initialized secure credential vault")
            except Exception as e:
                logger.error(f"Failed to initialize vault: {e}")
                self.vault = None
        else:
            self.vault = None
            logger.warning("No vault password provided - credential vault disabled")
    
    def require_auth(self, required_permission: Optional[str] = None):
        """Decorator for requiring authentication and authorization."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await self._handle_authenticated_request(
                    func, required_permission, *args, **kwargs
                )
            return wrapper
        return decorator
    
    def validate_input(self, validation_model: type):
        """Decorator for input validation using Pydantic models."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await self._handle_validated_request(
                    func, validation_model, *args, **kwargs
                )
            return wrapper
        return decorator
    
    def rate_limit(self, identifier_func: Callable = None):
        """Decorator for rate limiting."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await self._handle_rate_limited_request(
                    func, identifier_func, *args, **kwargs
                )
            return wrapper
        return decorator
    
    async def _handle_authenticated_request(self, func: Callable, required_permission: Optional[str], 
                                          *args, **kwargs) -> Any:
        """Handle request with authentication and authorization checks."""
        try:
            # Extract context from MCP call (this would need to be implemented based on MCP protocol)
            request_context = self._extract_request_context(args, kwargs)
            
            # Get authentication token
            auth_token = request_context.get('auth_token')
            if not auth_token:
                self.audit_logger.log_security_event(
                    "UNAUTHORIZED_ACCESS",
                    f"Missing auth token for {func.__name__}",
                    "WARNING"
                )
                raise PermissionError("Authentication required")
            
            # Verify token
            token_payload = self.token_manager.verify_token(auth_token)
            if not token_payload:
                self.audit_logger.log_security_event(
                    "INVALID_TOKEN",
                    f"Invalid token for {func.__name__}",
                    "WARNING"
                )
                raise PermissionError("Invalid authentication token")
            
            # Check permissions
            user_permissions = token_payload.get('permissions', [])
            if required_permission and not PermissionManager.check_permission(user_permissions, required_permission):
                self.audit_logger.log_security_event(
                    "INSUFFICIENT_PERMISSIONS",
                    f"User {token_payload['sub']} lacks permission {required_permission}",
                    "WARNING"
                )
                raise PermissionError(f"Permission {required_permission} required")
            
            # Add user context to kwargs
            kwargs['_user_context'] = {
                'user_id': token_payload['sub'],
                'permissions': user_permissions,
                'session_info': token_payload
            }
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Log successful API call
            self.audit_logger.log_api_call(
                token_payload['sub'],
                func.__name__,
                True,
                request_context.get('ip_address')
            )
            
            return result
            
        except Exception as e:
            # Log failed API call
            user_id = kwargs.get('_user_context', {}).get('user_id', 'unknown')
            self.audit_logger.log_api_call(
                user_id,
                func.__name__,
                False,
                request_context.get('ip_address'),
                str(e)
            )
            raise
    
    async def _handle_validated_request(self, func: Callable, validation_model: type, 
                                       *args, **kwargs) -> Any:
        """Handle request with input validation."""
        try:
            # Extract arguments for validation
            request_args = self._extract_request_arguments(args, kwargs)
            
            # Validate input using Pydantic model
            try:
                validated_input = validation_model(**request_args)
                
                # Replace arguments with validated ones
                kwargs.update(validated_input.dict())
                
            except Exception as validation_error:
                logger.warning(f"Validation failed for {func.__name__}: {validation_error}")
                self.audit_logger.log_security_event(
                    "INPUT_VALIDATION_FAILED",
                    f"Validation failed for {func.__name__}: {validation_error}",
                    "WARNING"
                )
                raise ValidationError(f"Input validation failed: {validation_error}")
            
            # Execute function with validated input
            return await func(*args, **kwargs)
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error in validated request for {func.__name__}: {e}")
            raise
    
    async def _handle_rate_limited_request(self, func: Callable, identifier_func: Optional[Callable], 
                                          *args, **kwargs) -> Any:
        """Handle request with rate limiting."""
        try:
            # Determine rate limit identifier
            if identifier_func:
                identifier = identifier_func(*args, **kwargs)
            else:
                # Use user ID from context if available
                user_context = kwargs.get('_user_context', {})
                identifier = user_context.get('user_id', 'anonymous')
            
            # Check rate limit
            if not self.rate_limiter.is_allowed(identifier):
                self.audit_logger.log_security_event(
                    "RATE_LIMIT_EXCEEDED",
                    f"Rate limit exceeded for {identifier} on {func.__name__}",
                    "WARNING"
                )
                raise PermissionError("Rate limit exceeded")
            
            # Execute function
            return await func(*args, **kwargs)
            
        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Error in rate limited request for {func.__name__}: {e}")
            raise
    
    def _extract_request_context(self, args: tuple, kwargs: dict) -> Dict[str, Any]:
        """Extract request context from MCP call."""
        # This would be implemented based on the actual MCP protocol
        # For now, return a minimal context
        return {
            'auth_token': kwargs.get('auth_token'),
            'ip_address': kwargs.get('client_ip'),
            'user_agent': kwargs.get('user_agent'),
            'timestamp': datetime.utcnow()
        }
    
    def _extract_request_arguments(self, args: tuple, kwargs: dict) -> Dict[str, Any]:
        """Extract arguments for validation from MCP call."""
        # Filter out internal parameters
        filtered_kwargs = {
            k: v for k, v in kwargs.items() 
            if not k.startswith('_') and k not in ['auth_token', 'client_ip', 'user_agent']
        }
        return filtered_kwargs
    
    async def authenticate_user(self, username: str, password: str) -> Optional[str]:
        """Authenticate user and return access token."""
        # In a real implementation, this would verify against a user database
        # For now, we'll use a simple hardcoded check
        
        if not username or not password:
            self.audit_logger.log_authentication(username or 'unknown', False)
            return None
        
        # Simulate user lookup and password verification
        # In production, this would hash and compare passwords
        valid_users = {
            'admin': ('admin_password', 'admin'),
            'user': ('user_password', 'user'),
            'readonly': ('readonly_password', 'readonly')
        }
        
        if username in valid_users:
            stored_password, role = valid_users[username]
            if password == stored_password:  # In production, use secure password hashing
                permissions = PermissionManager.get_permissions_for_role(role)
                token = self.token_manager.create_access_token(username, permissions)
                
                self.audit_logger.log_authentication(username, True)
                logger.info(f"User {username} authenticated successfully")
                
                return token
        
        self.audit_logger.log_authentication(username, False)
        logger.warning(f"Authentication failed for user {username}")
        return None
    
    def logout_user(self, auth_token: str):
        """Logout user by blacklisting token."""
        try:
            self.token_manager.blacklist_token(auth_token)
            logger.info("User logged out successfully")
        except Exception as e:
            logger.error(f"Error during logout: {e}")
    
    def get_user_permissions(self, auth_token: str) -> Optional[List[str]]:
        """Get user permissions from token."""
        token_payload = self.token_manager.verify_token(auth_token)
        if token_payload:
            return token_payload.get('permissions', [])
        return None
    
    async def store_secure_credential(self, key: str, credential: str, 
                                     metadata: Optional[Dict] = None):
        """Store credential in secure vault."""
        if not self.vault:
            raise RuntimeError("Secure vault not initialized")
        
        self.vault.store_credential(key, credential, metadata)
        logger.info(f"Stored secure credential: {key}")
    
    async def retrieve_secure_credential(self, key: str) -> Optional[str]:
        """Retrieve credential from secure vault."""
        if not self.vault:
            raise RuntimeError("Secure vault not initialized")
        
        credential = self.vault.retrieve_credential(key)
        if credential:
            logger.info(f"Retrieved secure credential: {key}")
        else:
            logger.warning(f"Credential not found: {key}")
        
        return credential
    
    def cleanup_expired_sessions(self):
        """Clean up expired sessions (should be called periodically)."""
        self.session_manager.cleanup_expired_sessions()

# Global security middleware instance
security = SecurityMiddleware()

# Convenience decorators
require_auth = security.require_auth
validate_input = security.validate_input
rate_limit = security.rate_limit