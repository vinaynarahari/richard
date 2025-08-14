"""
TLS/SSL configuration for secure MCP server communication.
Implements industry-standard secure communication protocols.
"""

import os
import ssl
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import datetime, timedelta
import ipaddress

logger = logging.getLogger(__name__)

class TLSConfig:
    """TLS/SSL configuration for secure MCP servers."""
    
    def __init__(self, cert_dir: str = "./security/certs"):
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        # Certificate paths
        self.ca_cert_path = self.cert_dir / "ca.crt"
        self.ca_key_path = self.cert_dir / "ca.key"
        self.server_cert_path = self.cert_dir / "server.crt"
        self.server_key_path = self.cert_dir / "server.key"
        self.client_cert_path = self.cert_dir / "client.crt"
        self.client_key_path = self.cert_dir / "client.key"
    
    def create_ca_certificate(self, common_name: str = "MCP-CA") -> None:
        """Create Certificate Authority certificate."""
        if self.ca_cert_path.exists() and self.ca_key_path.exists():
            logger.info("CA certificate already exists")
            return
        
        # Generate CA private key
        ca_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096
        )
        
        # Create CA certificate
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MCP Security"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Certificate Authority"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        
        ca_cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            subject  # Self-signed
        ).public_key(
            ca_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=3650)  # 10 years
        ).add_extension(
            x509.KeyUsage(
                key_cert_sign=True,
                crl_sign=True,
                digital_signature=False,
                key_encipherment=False,
                key_agreement=False,
                content_commitment=False,
                data_encipherment=False,
                encipher_only=False,
                decipher_only=False
            ),
            critical=True
        ).add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True
        ).sign(ca_key, hashes.SHA256())
        
        # Save CA certificate and key
        with open(self.ca_cert_path, "wb") as f:
            f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
        
        with open(self.ca_key_path, "wb") as f:
            f.write(ca_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Set restrictive permissions
        os.chmod(self.ca_key_path, 0o600)
        os.chmod(self.ca_cert_path, 0o644)
        
        logger.info("Created CA certificate")
    
    def create_server_certificate(self, hostname: str = "localhost", 
                                  alt_names: Optional[list] = None) -> None:
        """Create server certificate signed by CA."""
        if self.server_cert_path.exists() and self.server_key_path.exists():
            logger.info("Server certificate already exists")
            return
        
        # Load CA certificate and key
        with open(self.ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        
        with open(self.ca_key_path, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)
        
        # Generate server private key
        server_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        # Create server certificate
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MCP Security"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "MCP Servers"),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ])
        
        # Prepare Subject Alternative Names
        san_list = [x509.DNSName(hostname)]
        
        if alt_names:
            for alt_name in alt_names:
                if self._is_ip_address(alt_name):
                    san_list.append(x509.IPAddress(ipaddress.ip_address(alt_name)))
                else:
                    san_list.append(x509.DNSName(alt_name))
        
        # Add localhost variants
        san_list.extend([
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            x509.IPAddress(ipaddress.ip_address("::1"))
        ])
        
        server_cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            ca_cert.subject
        ).public_key(
            server_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365)  # 1 year
        ).add_extension(
            x509.KeyUsage(
                key_cert_sign=False,
                crl_sign=False,
                digital_signature=True,
                key_encipherment=True,
                key_agreement=False,
                content_commitment=True,
                data_encipherment=False,
                encipher_only=False,
                decipher_only=False
            ),
            critical=True
        ).add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH,
            ]),
            critical=True
        ).add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False
        ).sign(ca_key, hashes.SHA256())
        
        # Save server certificate and key
        with open(self.server_cert_path, "wb") as f:
            f.write(server_cert.public_bytes(serialization.Encoding.PEM))
        
        with open(self.server_key_path, "wb") as f:
            f.write(server_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Set restrictive permissions
        os.chmod(self.server_key_path, 0o600)
        os.chmod(self.server_cert_path, 0o644)
        
        logger.info("Created server certificate")
    
    def create_client_certificate(self, client_name: str = "mcp-client") -> None:
        """Create client certificate for mutual TLS authentication."""
        if self.client_cert_path.exists() and self.client_key_path.exists():
            logger.info("Client certificate already exists")
            return
        
        # Load CA certificate and key
        with open(self.ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        
        with open(self.ca_key_path, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)
        
        # Generate client private key
        client_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        # Create client certificate
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MCP Security"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "MCP Clients"),
            x509.NameAttribute(NameOID.COMMON_NAME, client_name),
        ])
        
        client_cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            ca_cert.subject
        ).public_key(
            client_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365)  # 1 year
        ).add_extension(
            x509.KeyUsage(
                key_cert_sign=False,
                crl_sign=False,
                digital_signature=True,
                key_encipherment=True,
                key_agreement=False,
                content_commitment=True,
                data_encipherment=False,
                encipher_only=False,
                decipher_only=False
            ),
            critical=True
        ).add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=True
        ).sign(ca_key, hashes.SHA256())
        
        # Save client certificate and key
        with open(self.client_cert_path, "wb") as f:
            f.write(client_cert.public_bytes(serialization.Encoding.PEM))
        
        with open(self.client_key_path, "wb") as f:
            f.write(client_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Set restrictive permissions
        os.chmod(self.client_key_path, 0o600)
        os.chmod(self.client_cert_path, 0o644)
        
        logger.info("Created client certificate")
    
    def create_ssl_context_server(self, require_client_cert: bool = True) -> ssl.SSLContext:
        """Create SSL context for server."""
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        
        # Load server certificate and key
        context.load_cert_chain(str(self.server_cert_path), str(self.server_key_path))
        
        if require_client_cert:
            # Load CA certificate for client verification
            context.load_verify_locations(str(self.ca_cert_path))
            context.verify_mode = ssl.CERT_REQUIRED
        else:
            context.verify_mode = ssl.CERT_NONE
        
        # Set secure protocol options
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        
        # Security options
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_TLSv1
        context.options |= ssl.OP_NO_TLSv1_1
        context.options |= ssl.OP_SINGLE_DH_USE
        context.options |= ssl.OP_SINGLE_ECDH_USE
        
        return context
    
    def create_ssl_context_client(self, verify_server: bool = True) -> ssl.SSLContext:
        """Create SSL context for client."""
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        
        if verify_server:
            # Load CA certificate for server verification
            context.load_verify_locations(str(self.ca_cert_path))
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
        else:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        
        # Load client certificate for mutual TLS
        if self.client_cert_path.exists() and self.client_key_path.exists():
            context.load_cert_chain(str(self.client_cert_path), str(self.client_key_path))
        
        # Set secure protocol options
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        
        return context
    
    def setup_certificates(self, hostname: str = "localhost", alt_names: Optional[list] = None):
        """Set up all certificates for secure communication."""
        logger.info("Setting up TLS certificates...")
        
        # Create CA certificate
        self.create_ca_certificate()
        
        # Create server certificate
        self.create_server_certificate(hostname, alt_names)
        
        # Create client certificate
        self.create_client_certificate()
        
        logger.info("TLS certificate setup complete")
    
    def get_certificate_info(self) -> Dict[str, Any]:
        """Get information about existing certificates."""
        info = {}
        
        cert_files = {
            'ca': self.ca_cert_path,
            'server': self.server_cert_path,
            'client': self.client_cert_path
        }
        
        for cert_type, cert_path in cert_files.items():
            if cert_path.exists():
                try:
                    with open(cert_path, 'rb') as f:
                        cert = x509.load_pem_x509_certificate(f.read())
                    
                    info[cert_type] = {
                        'subject': str(cert.subject),
                        'issuer': str(cert.issuer),
                        'serial_number': str(cert.serial_number),
                        'not_valid_before': cert.not_valid_before.isoformat(),
                        'not_valid_after': cert.not_valid_after.isoformat(),
                        'is_expired': cert.not_valid_after < datetime.utcnow()
                    }
                except Exception as e:
                    info[cert_type] = {'error': str(e)}
            else:
                info[cert_type] = {'status': 'not_found'}
        
        return info
    
    def _is_ip_address(self, value: str) -> bool:
        """Check if string is a valid IP address."""
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False