"""
Cryptographic utilities for secure MCP servers.
Implements encryption, key management, and secure communication protocols.
"""

import os
import secrets
import hashlib
import hmac
import base64
from typing import Optional, Tuple, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.backends import default_backend
import logging
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class SecureCrypto:
    """Cryptographic operations for MCP servers."""
    
    def __init__(self):
        self.backend = default_backend()
        
    def generate_key_pair(self) -> Tuple[bytes, bytes]:
        """Generate RSA key pair for asymmetric encryption."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=self.backend
        )
        
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return private_pem, public_pem
    
    def encrypt_asymmetric(self, message: bytes, public_key_pem: bytes) -> bytes:
        """Encrypt message using RSA public key."""
        public_key = serialization.load_pem_public_key(
            public_key_pem,
            backend=self.backend
        )
        
        ciphertext = public_key.encrypt(
            message,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return ciphertext
    
    def decrypt_asymmetric(self, ciphertext: bytes, private_key_pem: bytes) -> bytes:
        """Decrypt message using RSA private key."""
        private_key = serialization.load_pem_private_key(
            private_key_pem,
            password=None,
            backend=self.backend
        )
        
        plaintext = private_key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return plaintext
    
    def generate_symmetric_key(self) -> bytes:
        """Generate AES-256 key for symmetric encryption."""
        return secrets.token_bytes(32)  # 256 bits
    
    def encrypt_symmetric(self, message: bytes, key: bytes) -> Tuple[bytes, bytes]:
        """Encrypt message using AES-256-GCM."""
        iv = secrets.token_bytes(12)  # 96 bits for GCM
        
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv),
            backend=self.backend
        )
        
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(message) + encryptor.finalize()
        
        return ciphertext, iv + encryptor.tag  # Combine IV and auth tag
    
    def decrypt_symmetric(self, ciphertext: bytes, key: bytes, iv_and_tag: bytes) -> bytes:
        """Decrypt message using AES-256-GCM."""
        iv = iv_and_tag[:12]  # First 12 bytes are IV
        tag = iv_and_tag[12:]  # Remaining bytes are auth tag
        
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv, tag),
            backend=self.backend
        )
        
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        
        return plaintext
    
    def derive_key_from_password(self, password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """Derive encryption key from password using Scrypt."""
        if salt is None:
            salt = secrets.token_bytes(32)
        
        kdf = Scrypt(
            length=32,
            salt=salt,
            n=2**14,  # CPU/memory cost
            r=8,      # Block size
            p=1,      # Parallelization
            backend=self.backend
        )
        
        key = kdf.derive(password.encode())
        return key, salt
    
    def secure_hash(self, data: str, salt: Optional[bytes] = None) -> Tuple[str, bytes]:
        """Create secure hash using SHA-256 with salt."""
        if salt is None:
            salt = secrets.token_bytes(32)
        
        hasher = hashlib.sha256()
        hasher.update(salt)
        hasher.update(data.encode())
        
        return hasher.hexdigest(), salt
    
    def verify_hash(self, data: str, hash_value: str, salt: bytes) -> bool:
        """Verify hash against original data."""
        computed_hash, _ = self.secure_hash(data, salt)
        return hmac.compare_digest(computed_hash, hash_value)
    
    def generate_secure_token(self, length: int = 32) -> str:
        """Generate cryptographically secure random token."""
        return secrets.token_urlsafe(length)

class SecureVault:
    """Secure credential storage vault."""
    
    def __init__(self, vault_path: str, master_password: str):
        self.vault_path = vault_path
        self.crypto = SecureCrypto()
        
        # Derive encryption key from master password
        if os.path.exists(vault_path):
            self._load_vault(master_password)
        else:
            self._create_vault(master_password)
    
    def _create_vault(self, master_password: str):
        """Create a new secure vault."""
        self.encryption_key, self.salt = self.crypto.derive_key_from_password(master_password)
        
        # Create vault structure
        vault_data = {
            'version': '1.0',
            'created_at': datetime.utcnow().isoformat(),
            'credentials': {}
        }
        
        self._save_vault(vault_data)
        logger.info("Created new secure vault")
    
    def _load_vault(self, master_password: str):
        """Load existing vault."""
        with open(self.vault_path, 'rb') as f:
            encrypted_data = f.read()
        
        # Extract salt (first 32 bytes)
        self.salt = encrypted_data[:32]
        self.encryption_key, _ = self.crypto.derive_key_from_password(master_password, self.salt)
        
        # Decrypt vault data
        ciphertext = encrypted_data[32:64]  # Skip salt and IV+tag size
        iv_and_tag = encrypted_data[64:64+12+16]  # IV (12) + tag (16)
        
        try:
            decrypted = self.crypto.decrypt_symmetric(ciphertext, self.encryption_key, iv_and_tag)
            self.vault_data = json.loads(decrypted.decode())
            logger.info("Loaded secure vault")
        except Exception as e:
            logger.error(f"Failed to load vault: {e}")
            raise ValueError("Invalid master password or corrupted vault")
    
    def _save_vault(self, vault_data: Dict[str, Any]):
        """Save vault to disk."""
        # Serialize vault data
        serialized = json.dumps(vault_data).encode()
        
        # Encrypt vault data
        ciphertext, iv_and_tag = self.crypto.encrypt_symmetric(serialized, self.encryption_key)
        
        # Save: salt + ciphertext + iv_and_tag
        with open(self.vault_path, 'wb') as f:
            f.write(self.salt)
            f.write(ciphertext)
            f.write(iv_and_tag)
        
        self.vault_data = vault_data
    
    def store_credential(self, key: str, credential: str, metadata: Optional[Dict] = None):
        """Store encrypted credential."""
        # Encrypt credential
        cred_bytes = credential.encode()
        ciphertext, iv_and_tag = self.crypto.encrypt_symmetric(cred_bytes, self.encryption_key)
        
        # Store with metadata
        credential_data = {
            'ciphertext': base64.b64encode(ciphertext).decode(),
            'iv_and_tag': base64.b64encode(iv_and_tag).decode(),
            'created_at': datetime.utcnow().isoformat(),
            'metadata': metadata or {}
        }
        
        self.vault_data['credentials'][key] = credential_data
        self._save_vault(self.vault_data)
        
        logger.info(f"Stored credential: {key}")
    
    def retrieve_credential(self, key: str) -> Optional[str]:
        """Retrieve and decrypt credential."""
        if key not in self.vault_data['credentials']:
            return None
        
        cred_data = self.vault_data['credentials'][key]
        
        # Decrypt credential
        ciphertext = base64.b64decode(cred_data['ciphertext'])
        iv_and_tag = base64.b64decode(cred_data['iv_and_tag'])
        
        try:
            decrypted = self.crypto.decrypt_symmetric(ciphertext, self.encryption_key, iv_and_tag)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Failed to decrypt credential {key}: {e}")
            return None
    
    def list_credentials(self) -> Dict[str, Dict]:
        """List all credentials (metadata only, not values)."""
        result = {}
        for key, cred_data in self.vault_data['credentials'].items():
            result[key] = {
                'created_at': cred_data['created_at'],
                'metadata': cred_data['metadata']
            }
        return result
    
    def delete_credential(self, key: str) -> bool:
        """Delete a credential."""
        if key in self.vault_data['credentials']:
            del self.vault_data['credentials'][key]
            self._save_vault(self.vault_data)
            logger.info(f"Deleted credential: {key}")
            return True
        return False
    
    def change_master_password(self, old_password: str, new_password: str):
        """Change vault master password."""
        # Verify old password by trying to decrypt
        try:
            temp_key, _ = self.crypto.derive_key_from_password(old_password, self.salt)
            if temp_key != self.encryption_key:
                raise ValueError("Invalid old password")
        except:
            raise ValueError("Invalid old password")
        
        # Create new encryption key
        new_key, new_salt = self.crypto.derive_key_from_password(new_password)
        
        # Re-encrypt all credentials with new key
        for key, cred_data in self.vault_data['credentials'].items():
            # Decrypt with old key
            ciphertext = base64.b64decode(cred_data['ciphertext'])
            iv_and_tag = base64.b64decode(cred_data['iv_and_tag'])
            decrypted = self.crypto.decrypt_symmetric(ciphertext, self.encryption_key, iv_and_tag)
            
            # Encrypt with new key
            new_ciphertext, new_iv_and_tag = self.crypto.encrypt_symmetric(decrypted, new_key)
            
            # Update credential data
            cred_data['ciphertext'] = base64.b64encode(new_ciphertext).decode()
            cred_data['iv_and_tag'] = base64.b64encode(new_iv_and_tag).decode()
        
        # Update vault with new key
        self.encryption_key = new_key
        self.salt = new_salt
        self._save_vault(self.vault_data)
        
        logger.info("Changed vault master password")

class SecureSession:
    """Secure session management."""
    
    def __init__(self, session_timeout: int = 3600):  # 1 hour default
        self.sessions: Dict[str, Dict] = {}
        self.session_timeout = session_timeout
        self.crypto = SecureCrypto()
    
    def create_session(self, user_id: str, permissions: list) -> str:
        """Create a new secure session."""
        session_id = self.crypto.generate_secure_token(32)
        
        session_data = {
            'user_id': user_id,
            'permissions': permissions,
            'created_at': datetime.utcnow(),
            'last_activity': datetime.utcnow(),
            'ip_address': None,  # Would be set by server
            'user_agent': None   # Would be set by server
        }
        
        self.sessions[session_id] = session_data
        logger.info(f"Created session for user {user_id}")
        
        return session_id
    
    def validate_session(self, session_id: str) -> Optional[Dict]:
        """Validate and refresh session."""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        now = datetime.utcnow()
        
        # Check if session expired
        if (now - session['last_activity']).seconds > self.session_timeout:
            self.destroy_session(session_id)
            return None
        
        # Update last activity
        session['last_activity'] = now
        
        return session
    
    def destroy_session(self, session_id: str):
        """Destroy a session."""
        if session_id in self.sessions:
            user_id = self.sessions[session_id]['user_id']
            del self.sessions[session_id]
            logger.info(f"Destroyed session for user {user_id}")
    
    def cleanup_expired_sessions(self):
        """Clean up expired sessions."""
        now = datetime.utcnow()
        expired_sessions = []
        
        for session_id, session in self.sessions.items():
            if (now - session['last_activity']).seconds > self.session_timeout:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            self.destroy_session(session_id)
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")