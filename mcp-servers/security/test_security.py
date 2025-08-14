#!/usr/bin/env python3
"""
Comprehensive security test suite for MCP servers.
Tests authentication, authorization, input validation, encryption, and other security features.
"""

import asyncio
import os
import tempfile
import logging
from datetime import datetime, timedelta
import json
from pathlib import Path

# Custom assertion helper (since we don't have pytest)
def assert_raises(exception_class, func, *args, **kwargs):
    """Custom assert raises function."""
    try:
        func(*args, **kwargs)
        raise AssertionError(f"Expected {exception_class.__name__} but no exception was raised")
    except exception_class:
        pass  # Expected exception was raised

# Import security components
from auth import SecurityConfig, TokenManager, RateLimiter, PermissionManager, AuditLogger
from validation import SecurityValidator, ValidationError, DataType, GmailToolInput
from crypto import SecureCrypto, SecureVault, SecureSession
from middleware import SecurityMiddleware
from tls_config import TLSConfig

logger = logging.getLogger(__name__)

class TestSecurityConfig:
    """Test security configuration."""
    
    def test_config_initialization(self):
        """Test that security config initializes correctly."""
        config = SecurityConfig()
        
        assert config.JWT_ALGORITHM == 'HS256'
        assert config.JWT_EXPIRATION_DELTA.total_seconds() == 3600  # 1 hour
        assert config.RATE_LIMIT_REQUESTS > 0
        assert config.API_KEY_LENGTH > 0

class TestTokenManager:
    """Test JWT token management."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = SecurityConfig()
        self.token_manager = TokenManager(self.config)
    
    def test_create_access_token(self):
        """Test access token creation."""
        user_id = "test_user"
        permissions = ["gmail.read", "gmail.send"]
        
        token = self.token_manager.create_access_token(user_id, permissions)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are typically longer
    
    def test_verify_valid_token(self):
        """Test verification of valid token."""
        user_id = "test_user"
        permissions = ["gmail.read"]
        
        token = self.token_manager.create_access_token(user_id, permissions)
        payload = self.token_manager.verify_token(token)
        
        assert payload is not None
        assert payload['sub'] == user_id
        assert payload['permissions'] == permissions
        assert payload['type'] == 'access'
    
    def test_verify_invalid_token(self):
        """Test verification of invalid token."""
        invalid_token = "invalid.jwt.token"
        payload = self.token_manager.verify_token(invalid_token)
        
        assert payload is None
    
    def test_blacklist_token(self):
        """Test token blacklisting."""
        user_id = "test_user"
        permissions = ["gmail.read"]
        
        token = self.token_manager.create_access_token(user_id, permissions)
        
        # Verify token works
        payload = self.token_manager.verify_token(token)
        assert payload is not None
        
        # Blacklist token
        self.token_manager.blacklist_token(token)
        
        # Verify token no longer works
        payload = self.token_manager.verify_token(token)
        assert payload is None

class TestRateLimiter:
    """Test rate limiting functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = SecurityConfig()
        self.config.RATE_LIMIT_REQUESTS = 5  # Low limit for testing
        self.config.RATE_LIMIT_WINDOW = 60   # 1 minute
        self.rate_limiter = RateLimiter(self.config)
    
    def test_rate_limiting_allows_initial_requests(self):
        """Test that initial requests are allowed."""
        identifier = "test_user_1"
        
        for _ in range(5):
            assert self.rate_limiter.is_allowed(identifier) == True
    
    def test_rate_limiting_blocks_excess_requests(self):
        """Test that excess requests are blocked."""
        identifier = "test_user_2"
        
        # Use up all allowed requests
        for _ in range(5):
            self.rate_limiter.is_allowed(identifier)
        
        # Next request should be blocked
        assert self.rate_limiter.is_allowed(identifier) == False
    
    def test_rate_limiting_per_user(self):
        """Test that rate limiting is per user."""
        user1 = "test_user_3"
        user2 = "test_user_4"
        
        # Use up all requests for user1
        for _ in range(5):
            self.rate_limiter.is_allowed(user1)
        
        # user1 should be blocked
        assert self.rate_limiter.is_allowed(user1) == False
        
        # user2 should still be allowed
        assert self.rate_limiter.is_allowed(user2) == True

class TestSecurityValidator:
    """Test input validation and sanitization."""
    
    def test_validate_string(self):
        """Test string validation."""
        valid_string = "Hello, World!"
        result = SecurityValidator.validate_input(valid_string, DataType.STRING)
        assert result == "Hello, World!"
    
    def test_validate_string_with_dangerous_content(self):
        """Test that dangerous content is rejected."""
        dangerous_string = "<script>alert('xss')</script>"
        
        assert_raises(ValidationError, SecurityValidator.validate_input, dangerous_string, DataType.STRING)
    
    def test_validate_email(self):
        """Test email validation."""
        valid_email = "user@example.com"
        result = SecurityValidator.validate_input(valid_email, DataType.EMAIL)
        assert result == valid_email
        
        invalid_email = "not-an-email"
        assert_raises(ValidationError, SecurityValidator.validate_input, invalid_email, DataType.EMAIL)
    
    def test_validate_url(self):
        """Test URL validation."""
        valid_url = "https://example.com/path"
        result = SecurityValidator.validate_input(valid_url, DataType.URL)
        assert result == valid_url
        
        invalid_url = "javascript:alert(1)"
        assert_raises(ValidationError, SecurityValidator.validate_input, invalid_url, DataType.URL)
    
    def test_validate_json(self):
        """Test JSON validation."""
        valid_json = '{"key": "value"}'
        result = SecurityValidator.validate_input(valid_json, DataType.JSON)
        assert result == {"key": "value"}
        
        invalid_json = '{"invalid": json'
        assert_raises(ValidationError, SecurityValidator.validate_input, invalid_json, DataType.JSON)
    
    def test_gmail_input_validation(self):
        """Test Gmail input validation model."""
        valid_input = {
            "account": "user@gmail.com",
            "to": ["recipient@example.com"],
            "subject": "Test Subject",
            "body": "Test body content"
        }
        
        validated = GmailToolInput(**valid_input)
        assert validated.account == "user@gmail.com"
        assert validated.to == ["recipient@example.com"]
        assert validated.subject == "Test Subject"
        assert validated.body == "Test body content"
        
        # Test invalid input
        invalid_input = {
            "account": "not-an-email",
            "to": ["also-not-an-email"],
            "subject": "Test Subject",
            "body": "Test body"
        }
        
        assert_raises(Exception, GmailToolInput, **invalid_input)

class TestSecureCrypto:
    """Test cryptographic operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.crypto = SecureCrypto()
    
    def test_generate_key_pair(self):
        """Test RSA key pair generation."""
        private_key, public_key = self.crypto.generate_key_pair()
        
        assert private_key is not None
        assert public_key is not None
        assert b'-----BEGIN PRIVATE KEY-----' in private_key
        assert b'-----BEGIN PUBLIC KEY-----' in public_key
    
    def test_asymmetric_encryption(self):
        """Test RSA encryption/decryption."""
        private_key, public_key = self.crypto.generate_key_pair()
        message = b"Secret message for testing"
        
        # Encrypt with public key
        ciphertext = self.crypto.encrypt_asymmetric(message, public_key)
        assert ciphertext != message
        
        # Decrypt with private key
        plaintext = self.crypto.decrypt_asymmetric(ciphertext, private_key)
        assert plaintext == message
    
    def test_symmetric_encryption(self):
        """Test AES encryption/decryption."""
        key = self.crypto.generate_symmetric_key()
        message = b"Another secret message for testing"
        
        # Encrypt
        ciphertext, iv_and_tag = self.crypto.encrypt_symmetric(message, key)
        assert ciphertext != message
        
        # Decrypt
        plaintext = self.crypto.decrypt_symmetric(ciphertext, key, iv_and_tag)
        assert plaintext == message
    
    def test_password_key_derivation(self):
        """Test key derivation from password."""
        password = "strong_test_password_123!"
        
        key1, salt1 = self.crypto.derive_key_from_password(password)
        key2, salt2 = self.crypto.derive_key_from_password(password, salt1)
        
        # Same password and salt should produce same key
        assert key1 == key2
        assert salt1 == salt2
        
        # Different salt should produce different key
        key3, salt3 = self.crypto.derive_key_from_password(password)
        assert key1 != key3
        assert salt1 != salt3
    
    def test_secure_hash(self):
        """Test secure hashing."""
        data = "sensitive data to hash"
        
        hash1, salt1 = self.crypto.secure_hash(data)
        hash2, salt2 = self.crypto.secure_hash(data)
        
        # Same data should produce different hashes with different salts
        assert hash1 != hash2
        assert salt1 != salt2
        
        # Verify hash
        assert self.crypto.verify_hash(data, hash1, salt1) == True
        assert self.crypto.verify_hash(data, hash2, salt2) == True
        assert self.crypto.verify_hash("wrong data", hash1, salt1) == False

class TestSecureVault:
    """Test secure credential vault."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.vault_path = os.path.join(self.temp_dir, "test_vault.enc")
        self.master_password = "secure_master_password_123!"
    
    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.vault_path):
            os.remove(self.vault_path)
        os.rmdir(self.temp_dir)
    
    def test_vault_creation(self):
        """Test vault creation."""
        vault = SecureVault(self.vault_path, self.master_password)
        assert os.path.exists(self.vault_path)
        assert vault.vault_data['version'] == '1.0'
    
    def test_credential_storage_and_retrieval(self):
        """Test storing and retrieving credentials."""
        vault = SecureVault(self.vault_path, self.master_password)
        
        # Store credential
        credential_key = "test_api_key"
        credential_value = "secret_api_key_12345"
        vault.store_credential(credential_key, credential_value)
        
        # Retrieve credential
        retrieved = vault.retrieve_credential(credential_key)
        assert retrieved == credential_value
        
        # Try to retrieve non-existent credential
        not_found = vault.retrieve_credential("non_existent")
        assert not_found is None
    
    def test_vault_loading(self):
        """Test loading existing vault."""
        # Create vault and store credential
        vault1 = SecureVault(self.vault_path, self.master_password)
        vault1.store_credential("test_key", "test_value")
        
        # Load vault from disk
        vault2 = SecureVault(self.vault_path, self.master_password)
        retrieved = vault2.retrieve_credential("test_key")
        assert retrieved == "test_value"
    
    def test_wrong_master_password(self):
        """Test that wrong master password fails."""
        vault1 = SecureVault(self.vault_path, self.master_password)
        vault1.store_credential("test_key", "test_value")
        
        # Try to load with wrong password
        assert_raises(ValueError, SecureVault, self.vault_path, "wrong_password")

class TestTLSConfig:
    """Test TLS configuration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tls_config = TLSConfig(self.temp_dir)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_certificate_creation(self):
        """Test certificate creation."""
        self.tls_config.setup_certificates()
        
        # Check that certificates were created
        assert self.tls_config.ca_cert_path.exists()
        assert self.tls_config.ca_key_path.exists()
        assert self.tls_config.server_cert_path.exists()
        assert self.tls_config.server_key_path.exists()
        assert self.tls_config.client_cert_path.exists()
        assert self.tls_config.client_key_path.exists()
    
    def test_ssl_context_creation(self):
        """Test SSL context creation."""
        self.tls_config.setup_certificates()
        
        # Create server context
        server_context = self.tls_config.create_ssl_context_server()
        assert server_context is not None
        assert server_context.minimum_version.name == 'TLSv1_2'
        
        # Create client context
        client_context = self.tls_config.create_ssl_context_client()
        assert client_context is not None
        assert client_context.minimum_version.name == 'TLSv1_2'
    
    def test_certificate_info(self):
        """Test certificate information retrieval."""
        self.tls_config.setup_certificates()
        
        cert_info = self.tls_config.get_certificate_info()
        
        assert 'ca' in cert_info
        assert 'server' in cert_info
        assert 'client' in cert_info
        
        for cert_type in ['ca', 'server', 'client']:
            assert 'subject' in cert_info[cert_type]
            assert 'issuer' in cert_info[cert_type]
            assert 'not_valid_before' in cert_info[cert_type]
            assert 'not_valid_after' in cert_info[cert_type]

def run_security_tests():
    """Run all security tests."""
    print("🔒 Running Security Test Suite")
    print("=" * 50)
    
    test_classes = [
        TestSecurityConfig,
        TestTokenManager,
        TestRateLimiter,
        TestSecurityValidator,
        TestSecureCrypto,
        TestSecureVault,
        TestTLSConfig
    ]
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    for test_class in test_classes:
        print(f"\n🧪 Testing {test_class.__name__}")
        
        test_instance = test_class()
        
        # Get all test methods
        test_methods = [method for method in dir(test_instance) if method.startswith('test_')]
        
        for method_name in test_methods:
            total_tests += 1
            print(f"  • {method_name}...", end=" ")
            
            try:
                # Run setup if it exists
                if hasattr(test_instance, 'setup_method'):
                    test_instance.setup_method()
                
                # Run the test
                method = getattr(test_instance, method_name)
                method()
                
                # Run teardown if it exists
                if hasattr(test_instance, 'teardown_method'):
                    test_instance.teardown_method()
                
                print("✅ PASS")
                passed_tests += 1
                
            except Exception as e:
                print(f"❌ FAIL: {e}")
                failed_tests.append(f"{test_class.__name__}.{method_name}: {e}")
    
    print(f"\n📊 Test Results")
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {len(failed_tests)}")
    
    if failed_tests:
        print(f"\n❌ Failed Tests:")
        for failure in failed_tests:
            print(f"  • {failure}")
    else:
        print(f"\n🎉 All tests passed!")
    
    return len(failed_tests) == 0

if __name__ == "__main__":
    success = run_security_tests()
    exit(0 if success else 1)