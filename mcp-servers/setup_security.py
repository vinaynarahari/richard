#!/usr/bin/env python3
"""
Security setup script for MCP servers.
Initializes all security components and performs security validation.
"""

import os
import sys
import getpass
import logging
from pathlib import Path

# Add security module to path
sys.path.append('./security')

from security.tls_config import TLSConfig
from security.crypto import SecureVault
from security.auth import SecurityConfig
from security.middleware import SecurityMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_directories():
    """Create required security directories."""
    directories = [
        './security/certs',
        './security/logs',
        './logs'
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {directory}")

def setup_tls_certificates():
    """Set up TLS certificates for secure communication."""
    logger.info("🔐 Setting up TLS certificates...")
    
    tls_config = TLSConfig()
    
    # Get hostname from user
    hostname = input("Enter server hostname (default: localhost): ").strip()
    if not hostname:
        hostname = "localhost"
    
    # Get alternative names
    alt_names_input = input("Enter alternative hostnames (comma-separated, optional): ").strip()
    alt_names = [name.strip() for name in alt_names_input.split(",") if name.strip()] if alt_names_input else None
    
    # Set up certificates
    tls_config.setup_certificates(hostname, alt_names)
    
    # Display certificate info
    cert_info = tls_config.get_certificate_info()
    for cert_type, info in cert_info.items():
        if 'subject' in info:
            logger.info(f"✅ {cert_type.upper()} certificate: {info['subject']}")
            logger.info(f"   Valid until: {info['not_valid_after']}")

def setup_secure_vault():
    """Set up secure credential vault."""
    logger.info("🔒 Setting up secure credential vault...")
    
    vault_path = "./security/vault.enc"
    
    # Get master password
    while True:
        password1 = getpass.getpass("Enter vault master password: ")
        if len(password1) < 12:
            print("❌ Password must be at least 12 characters")
            continue
        
        password2 = getpass.getpass("Confirm vault master password: ")
        if password1 != password2:
            print("❌ Passwords don't match")
            continue
        
        break
    
    try:
        vault = SecureVault(vault_path, password1)
        logger.info("✅ Secure vault created successfully")
        
        # Store vault password in environment file
        env_path = Path("./.env.security")
        with open(env_path, "w") as f:
            f.write(f"SECURITY_VAULT_PASSWORD={password1}\n")
        
        # Set restrictive permissions
        os.chmod(env_path, 0o600)
        logger.info("✅ Vault password stored in .env.security")
        
        return vault
        
    except Exception as e:
        logger.error(f"❌ Failed to create vault: {e}")
        return None

def setup_jwt_secret():
    """Set up JWT secret key."""
    logger.info("🔑 Setting up JWT secret key...")
    
    from security.auth import SecurityConfig
    config = SecurityConfig()
    
    env_path = Path("./.env.security")
    with open(env_path, "a") as f:
        f.write(f"JWT_SECRET_KEY={config.JWT_SECRET_KEY}\n")
    
    logger.info("✅ JWT secret key generated and stored")

def setup_example_credentials(vault):
    """Set up example credentials in vault."""
    if not vault:
        return
    
    logger.info("📝 Setting up example credentials...")
    
    # Store some example credentials
    examples = [
        ("gmail_api_key", "example_gmail_api_key_here"),
        ("notion_token", "example_notion_token_here"),
        ("google_search_key", "example_search_api_key_here")
    ]
    
    for key, value in examples:
        vault.store_credential(key, value, {"type": "api_key", "service": key.split("_")[0]})
        logger.info(f"✅ Stored example credential: {key}")

def validate_security_setup():
    """Validate the security setup."""
    logger.info("🧪 Validating security setup...")
    
    # Check TLS certificates
    tls_config = TLSConfig()
    cert_info = tls_config.get_certificate_info()
    
    for cert_type in ['ca', 'server', 'client']:
        if cert_type in cert_info and 'subject' in cert_info[cert_type]:
            logger.info(f"✅ {cert_type.upper()} certificate valid")
        else:
            logger.warning(f"⚠️  {cert_type.upper()} certificate missing or invalid")
    
    # Check vault
    vault_path = "./security/vault.enc"
    if Path(vault_path).exists():
        logger.info("✅ Secure vault exists")
    else:
        logger.warning("⚠️  Secure vault not found")
    
    # Check environment file
    env_path = Path("./.env.security")
    if env_path.exists():
        logger.info("✅ Security environment file exists")
    else:
        logger.warning("⚠️  Security environment file not found")
    
    # Test security middleware
    try:
        middleware = SecurityMiddleware()
        logger.info("✅ Security middleware initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️  Security middleware error: {e}")

def display_next_steps():
    """Display next steps for the user."""
    print("\n" + "="*60)
    print("🎉 Security Setup Complete!")
    print("="*60)
    
    print("\n📋 Next Steps:")
    print("1. Update your MCP servers to use the security middleware")
    print("2. Configure your MCP clients to use TLS certificates")
    print("3. Set up monitoring and alerting for security events")
    print("4. Review and customize security policies in security/config.yaml")
    print("5. Run security tests: python security/test_security.py")
    
    print("\n🔐 Security Files Created:")
    print("• ./security/certs/         - TLS certificates")
    print("• ./security/vault.enc      - Encrypted credential vault")
    print("• ./.env.security          - Security environment variables")
    print("• ./security/config.yaml   - Security policies")
    print("• ./logs/                  - Audit logs directory")
    
    print("\n⚠️  Important Security Notes:")
    print("• Keep your vault master password secure")
    print("• Back up your TLS certificates")
    print("• Regularly rotate API keys and certificates")
    print("• Monitor audit logs for suspicious activity")
    print("• Update security configurations for production use")
    
    print("\n📚 Documentation:")
    print("• See SECURITY.md for detailed security information")
    print("• Review security/config.yaml for configuration options")

def main():
    """Main setup function."""
    print("🔒 MCP Servers Security Setup")
    print("=" * 40)
    
    try:
        # Create directories
        setup_directories()
        
        # Set up TLS certificates
        setup_tls_certificates()
        
        # Set up secure vault
        vault = setup_secure_vault()
        
        # Set up JWT secret
        setup_jwt_secret()
        
        # Set up example credentials
        setup_example_credentials(vault)
        
        # Validate setup
        validate_security_setup()
        
        # Display next steps
        display_next_steps()
        
    except KeyboardInterrupt:
        print("\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()