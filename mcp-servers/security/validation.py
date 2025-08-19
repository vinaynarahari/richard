"""
Input validation and sanitization for MCP servers.
Implements comprehensive validation to prevent injection attacks,
data corruption, and other security vulnerabilities.
"""

import re
import json
import html
import urllib.parse
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import logging
from pydantic import BaseModel, validator, EmailStr
from datetime import datetime
import bleach

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Custom validation error."""
    pass

class DataType(Enum):
    """Supported data types for validation."""
    STRING = "string"
    EMAIL = "email"
    URL = "url"
    HTML = "html" 
    JSON = "json"
    SQL = "sql"
    FILENAME = "filename"
    DATABASE_ID = "database_id"
    MESSAGE_ID = "message_id"
    QUERY = "query"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    DATETIME = "datetime"

class SecurityValidator:
    """Comprehensive input validation and sanitization."""
    
    # Regex patterns for validation
    PATTERNS = {
        'email': re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),
        'url': re.compile(r'^https?://[a-zA-Z0-9.-]+(?:\.[a-zA-Z]{2,})?(?:/.*)?$'),
        'database_id': re.compile(r'^[a-zA-Z0-9_-]{32}$'),
        'message_id': re.compile(r'^[a-zA-Z0-9_-]+$'),
        'filename': re.compile(r'^[a-zA-Z0-9._-]+$'),
        'alphanumeric': re.compile(r'^[a-zA-Z0-9]+$'),
        'uuid': re.compile(r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$')
    }
    
    # Dangerous patterns that should be rejected
    DANGEROUS_PATTERNS = [
        re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
        re.compile(r'javascript:', re.IGNORECASE),
        re.compile(r'on\w+\s*=', re.IGNORECASE),
        re.compile(r'(union|select|insert|update|delete|drop|create|alter)\s', re.IGNORECASE),
        re.compile(r'[;&|`]', re.IGNORECASE),  # Command injection
        re.compile(r'\.\./', re.IGNORECASE),   # Directory traversal
        re.compile(r'\\x[0-9a-f]{2}', re.IGNORECASE),  # Hex encoding
    ]
    
    # Maximum lengths for different data types
    MAX_LENGTHS = {
        'short_string': 255,
        'medium_string': 1000,
        'long_string': 10000,
        'query': 1000,
        'subject': 255,
        'body': 50000,
        'filename': 255,
        'url': 2000
    }
    
    @classmethod
    def validate_input(cls, value: Any, data_type: DataType, 
                      max_length: Optional[int] = None,
                      allow_empty: bool = False) -> Any:
        """Validate and sanitize input based on data type."""
        
        if value is None:
            if allow_empty:
                return None
            else:
                raise ValidationError("Value cannot be None")
        
        if data_type == DataType.STRING:
            return cls._validate_string(value, max_length or cls.MAX_LENGTHS['medium_string'])
        elif data_type == DataType.EMAIL:
            return cls._validate_email(value)
        elif data_type == DataType.URL:
            return cls._validate_url(value)
        elif data_type == DataType.HTML:
            return cls._sanitize_html(value)
        elif data_type == DataType.JSON:
            return cls._validate_json(value)
        elif data_type == DataType.SQL:
            return cls._validate_sql(value)
        elif data_type == DataType.FILENAME:
            return cls._validate_filename(value)
        elif data_type == DataType.DATABASE_ID:
            return cls._validate_database_id(value)
        elif data_type == DataType.MESSAGE_ID:
            return cls._validate_message_id(value)
        elif data_type == DataType.QUERY:
            return cls._validate_query(value)
        elif data_type == DataType.INTEGER:
            return cls._validate_integer(value)
        elif data_type == DataType.BOOLEAN:
            return cls._validate_boolean(value)
        elif data_type == DataType.DATETIME:
            return cls._validate_datetime(value)
        else:
            raise ValidationError(f"Unknown data type: {data_type}")
    
    @classmethod
    def _validate_string(cls, value: Any, max_length: int) -> str:
        """Validate and sanitize a string."""
        if not isinstance(value, str):
            try:
                value = str(value)
            except:
                raise ValidationError("Cannot convert to string")
        
        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if pattern.search(value):
                logger.warning(f"Dangerous pattern detected in string: {pattern.pattern}")
                raise ValidationError("Input contains potentially dangerous content")
        
        # Length validation
        if len(value) > max_length:
            raise ValidationError(f"String too long (max {max_length} characters)")
        
        # Basic sanitization
        value = html.escape(value)
        return value.strip()
    
    @classmethod
    def _validate_email(cls, value: str) -> str:
        """Validate email address."""
        if not isinstance(value, str):
            raise ValidationError("Email must be a string")
        
        value = value.strip().lower()
        
        if not cls.PATTERNS['email'].match(value):
            raise ValidationError("Invalid email format")
        
        if len(value) > cls.MAX_LENGTHS['short_string']:
            raise ValidationError("Email too long")
        
        return value
    
    @classmethod
    def _validate_url(cls, value: str) -> str:
        """Validate URL."""
        if not isinstance(value, str):
            raise ValidationError("URL must be a string")
        
        value = value.strip()
        
        if not cls.PATTERNS['url'].match(value):
            raise ValidationError("Invalid URL format")
        
        if len(value) > cls.MAX_LENGTHS['url']:
            raise ValidationError("URL too long")
        
        # Additional security checks
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme not in ['http', 'https']:
            raise ValidationError("Only HTTP and HTTPS URLs allowed")
        
        return value
    
    @classmethod
    def _sanitize_html(cls, value: str) -> str:
        """Sanitize HTML content."""
        if not isinstance(value, str):
            raise ValidationError("HTML content must be a string")
        
        # Allowed tags and attributes for safe HTML
        allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']
        allowed_attributes = {}
        
        # Use bleach to sanitize HTML
        sanitized = bleach.clean(
            value,
            tags=allowed_tags,
            attributes=allowed_attributes,
            strip=True
        )
        
        return sanitized
    
    @classmethod
    def _validate_json(cls, value: Union[str, dict, list]) -> Union[dict, list]:
        """Validate JSON data."""
        if isinstance(value, (dict, list)):
            return value
        
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                # Limit JSON size to prevent DoS
                if len(json.dumps(parsed)) > cls.MAX_LENGTHS['long_string']:
                    raise ValidationError("JSON too large")
                return parsed
            except json.JSONDecodeError:
                raise ValidationError("Invalid JSON format")
        
        raise ValidationError("Invalid JSON type")
    
    @classmethod
    def _validate_sql(cls, value: str) -> str:
        """Validate SQL queries (very restrictive)."""
        if not isinstance(value, str):
            raise ValidationError("SQL must be a string")
        
        # For security, we're very restrictive with SQL
        # Only allow SELECT statements with basic operations
        value = value.strip()
        
        # Check for dangerous SQL keywords
        dangerous_keywords = ['insert', 'update', 'delete', 'drop', 'create', 'alter', 'exec', 'execute']
        for keyword in dangerous_keywords:
            if re.search(rf'\b{keyword}\b', value, re.IGNORECASE):
                raise ValidationError(f"SQL keyword '{keyword}' not allowed")
        
        return value
    
    @classmethod
    def _validate_filename(cls, value: str) -> str:
        """Validate filename."""
        if not isinstance(value, str):
            raise ValidationError("Filename must be a string")
        
        value = value.strip()
        
        if not cls.PATTERNS['filename'].match(value):
            raise ValidationError("Invalid filename format")
        
        if len(value) > cls.MAX_LENGTHS['filename']:
            raise ValidationError("Filename too long")
        
        # Prevent directory traversal
        if '..' in value or '/' in value or '\\' in value:
            raise ValidationError("Filename contains invalid characters")
        
        return value
    
    @classmethod
    def _validate_database_id(cls, value: str) -> str:
        """Validate Notion database ID."""
        if not isinstance(value, str):
            raise ValidationError("Database ID must be a string")
        
        value = value.strip()
        
        # Remove hyphens for validation
        clean_id = value.replace('-', '')
        
        if len(clean_id) != 32 or not clean_id.isalnum():
            raise ValidationError("Invalid database ID format")
        
        return value
    
    @classmethod
    def _validate_message_id(cls, value: str) -> str:
        """Validate email message ID."""
        if not isinstance(value, str):
            raise ValidationError("Message ID must be a string")
        
        value = value.strip()
        
        if not cls.PATTERNS['message_id'].match(value):
            raise ValidationError("Invalid message ID format")
        
        if len(value) > 255:
            raise ValidationError("Message ID too long")
        
        return value
    
    @classmethod
    def _validate_query(cls, value: str) -> str:
        """Validate search query."""
        if not isinstance(value, str):
            raise ValidationError("Query must be a string")
        
        value = value.strip()
        
        if len(value) > cls.MAX_LENGTHS['query']:
            raise ValidationError("Query too long")
        
        # Remove potentially dangerous characters
        dangerous_chars = ['<', '>', '{', '}', '[', ']', '|', '&', ';']
        for char in dangerous_chars:
            if char in value:
                raise ValidationError(f"Query contains invalid character: {char}")
        
        return value
    
    @classmethod
    def _validate_integer(cls, value: Any) -> int:
        """Validate integer."""
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ValidationError("Invalid integer value")
    
    @classmethod
    def _validate_boolean(cls, value: Any) -> bool:
        """Validate boolean."""
        if isinstance(value, bool):
            return value
        
        if isinstance(value, str):
            if value.lower() in ['true', '1', 'yes', 'on']:
                return True
            elif value.lower() in ['false', '0', 'no', 'off']:
                return False
        
        raise ValidationError("Invalid boolean value")
    
    @classmethod
    def _validate_datetime(cls, value: Any) -> datetime:
        """Validate datetime."""
        if isinstance(value, datetime):
            return value
        
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError("Invalid datetime format")
        
        raise ValidationError("Invalid datetime type")

# Pydantic models for structured validation
class GmailToolInput(BaseModel):
    """Validation model for Gmail tool inputs."""
    account: EmailStr
    to: List[EmailStr] = None
    subject: str = None
    body: str = None
    message_id: str = None
    query: str = None
    max_results: int = 10
    
    @validator('subject')
    def validate_subject(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.STRING, max_length=255)
        return v
    
    @validator('body')
    def validate_body(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.HTML, max_length=50000)
        return v
    
    @validator('message_id')
    def validate_message_id(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.MESSAGE_ID)
        return v
    
    @validator('query')
    def validate_query(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.QUERY)
        return v
    
    @validator('max_results')
    def validate_max_results(cls, v):
        if v < 1 or v > 100:
            raise ValueError('max_results must be between 1 and 100')
        return v

class NotionToolInput(BaseModel):
    """Validation model for Notion tool inputs."""
    database_id: str = None
    page_id: str = None
    properties: Dict = None
    filter: Dict = None
    sorts: List[Dict] = None
    children: List[Dict] = None
    query: str = None
    page_size: int = 10
    
    @validator('database_id')
    def validate_database_id(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.DATABASE_ID)
        return v
    
    @validator('page_id')
    def validate_page_id(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.DATABASE_ID)  # Same format
        return v
    
    @validator('properties')
    def validate_properties(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.JSON)
        return v
    
    @validator('filter')
    def validate_filter(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.JSON)
        return v
    
    @validator('sorts')
    def validate_sorts(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.JSON)
        return v
    
    @validator('children')
    def validate_children(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.JSON)
        return v
    
    @validator('query')
    def validate_query(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.QUERY)
        return v
    
    @validator('page_size')
    def validate_page_size(cls, v):
        if v < 1 or v > 100:
            raise ValueError('page_size must be between 1 and 100')
        return v

class SearchToolInput(BaseModel):
    """Validation model for Search tool inputs."""
    query: str
    num_results: int = 10
    start_index: int = 1
    site_search: str = None
    file_type: str = None
    date_restrict: str = None
    image_size: str = None
    image_type: str = None
    safe_search: str = "active"
    sort_by: str = "relevance"
    
    @validator('query')
    def validate_query(cls, v):
        return SecurityValidator.validate_input(v, DataType.QUERY)
    
    @validator('num_results')
    def validate_num_results(cls, v):
        if v < 1 or v > 100:
            raise ValueError('num_results must be between 1 and 100')
        return v
    
    @validator('start_index')
    def validate_start_index(cls, v):
        if v < 1:
            raise ValueError('start_index must be positive')
        return v
    
    @validator('site_search')
    def validate_site_search(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.URL)
        return v
    
    @validator('file_type')
    def validate_file_type(cls, v):
        if v is not None:
            allowed_types = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt']
            if v.lower() not in allowed_types:
                raise ValueError(f'file_type must be one of: {allowed_types}')
        return v
    
    @validator('safe_search')
    def validate_safe_search(cls, v):
        if v not in ['active', 'off']:
            raise ValueError('safe_search must be "active" or "off"')
        return v

class BrowserToolInput(BaseModel):
    """Validation model for Browser automation tool inputs."""
    url: str = None
    query: str = None
    action: str = None
    target: str = None
    value: str = None
    max_results: int = 10
    timeout: int = 30
    wait_for: str = None
    screenshot: bool = False
    
    @validator('url')
    def validate_url(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.URL)
        return v
    
    @validator('query')
    def validate_query(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.QUERY)
        return v
    
    @validator('action')
    def validate_action(cls, v):
        if v is not None:
            allowed_actions = ['click', 'type', 'select', 'hover', 'wait', 'navigate', 'scroll', 'screenshot']
            if v.lower() not in allowed_actions:
                raise ValueError(f'action must be one of: {allowed_actions}')
            return v.lower()
        return v
    
    @validator('target')
    def validate_target(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.STRING, max_length=1000)
        return v
    
    @validator('value')
    def validate_value(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.STRING, max_length=5000)
        return v
    
    @validator('max_results')
    def validate_max_results(cls, v):
        if v < 1 or v > 50:
            raise ValueError('max_results must be between 1 and 50')
        return v
    
    @validator('timeout')
    def validate_timeout(cls, v):
        if v < 1 or v > 300:
            raise ValueError('timeout must be between 1 and 300 seconds')
        return v
    
    @validator('wait_for')
    def validate_wait_for(cls, v):
        if v is not None:
            return SecurityValidator.validate_input(v, DataType.STRING, max_length=500)
        return v