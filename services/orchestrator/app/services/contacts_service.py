"""
macOS Contacts integration service for retrieving contact information
"""

import subprocess
import json
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class Contact:
    def __init__(self, name: str, phone_numbers: List[str], emails: List[str] = None):
        self.name = name
        self.phone_numbers = phone_numbers or []
        self.emails = emails or []
        
    def get_primary_phone(self) -> Optional[str]:
        """Get the primary phone number (mobile preferred)"""
        if not self.phone_numbers:
            return None
        
        # Prefer mobile numbers
        for phone in self.phone_numbers:
            phone_clean = phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
            if phone_clean:
                return phone_clean
        
        return self.phone_numbers[0] if self.phone_numbers else None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "phone_numbers": self.phone_numbers,
            "emails": self.emails,
            "primary_phone": self.get_primary_phone()
        }


class ContactsService:
    """Service to interact with macOS Contacts app"""
    
    def __init__(self):
        self._contacts_cache: Optional[List[Contact]] = None
    
    async def get_all_contacts(self) -> List[Contact]:
        """Get all contacts from macOS Contacts app"""
        if self._contacts_cache is not None:
            return self._contacts_cache
            
        try:
            # Use AppleScript to get contacts from Contacts app (limit to first 100 for speed)
            applescript = '''
            set contactsList to ""
            set contactCount to 0
            tell application "Contacts"
                repeat with aPerson in people
                    set contactCount to contactCount + 1
                    if contactCount > 100 then exit repeat
                    
                    try
                        set personName to name of aPerson
                        if personName is not "" then
                            set phoneNumbers to ""
                            repeat with aPhone in phones of aPerson
                                set phoneValue to value of aPhone
                                if phoneNumbers is "" then
                                    set phoneNumbers to phoneValue
                                else
                                    set phoneNumbers to phoneNumbers & "|" & phoneValue
                                end if
                            end repeat
                            
                            if phoneNumbers is not "" then
                                if contactsList is "" then
                                    set contactsList to personName & ":" & phoneNumbers
                                else
                                    set contactsList to contactsList & "\\n" & personName & ":" & phoneNumbers
                                end if
                            end if
                        end if
                    end try
                end repeat
            end tell
            return contactsList
            '''
            
            result = subprocess.run(
                ['osascript', '-e', applescript],
                capture_output=True,
                text=True,
                timeout=10  # Reduced timeout
            )
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    # Parse the simple format: "Name:phone1|phone2|phone3\nName2:phone..."
                    contacts_text = result.stdout.strip()
                    contacts = []
                    
                    for line in contacts_text.split('\n'):
                        if ':' in line:
                            name, phones_str = line.split(':', 1)
                            phones = [p.strip() for p in phones_str.split('|') if p.strip()]
                            
                            if name.strip() and phones:
                                contacts.append(Contact(name.strip(), phones, []))
                    
                    self._contacts_cache = contacts
                    logger.info(f"Loaded {len(contacts)} contacts from macOS Contacts")
                    return contacts
                    
                except Exception as e:
                    logger.error(f"Failed to parse contacts data: {e}")
                    logger.error(f"Raw output: {result.stdout}")
                    
            else:
                logger.error(f"AppleScript failed: {result.stderr}")
                
        except Exception as e:
            logger.error(f"Failed to get contacts: {e}")
        
        return []
    
    async def find_contact_by_name(self, query: str, fuzzy: bool = True) -> Optional[Contact]:
        """Find a contact by name with optional fuzzy matching"""
        contacts = await self.get_all_contacts()
        
        if not contacts:
            return None
            
        query_lower = query.lower().strip()
        
        # First try exact match
        for contact in contacts:
            if contact.name.lower().strip() == query_lower:
                return contact
        
        # Then try fuzzy matching if enabled
        if fuzzy:
            import difflib
            contact_names = [c.name.lower().strip() for c in contacts]
            matches = difflib.get_close_matches(query_lower, contact_names, n=1, cutoff=0.6)
            
            if matches:
                for contact in contacts:
                    if contact.name.lower().strip() == matches[0]:
                        return contact
        
        return None
    
    async def get_contact_suggestions(self, query: str, max_results: int = 5) -> List[Contact]:
        """Get contact suggestions based on partial name match"""
        contacts = await self.get_all_contacts()
        
        if not contacts:
            return []
            
        query_lower = query.lower().strip()
        suggestions = []
        
        # Find contacts that contain the query string
        for contact in contacts:
            name_lower = contact.name.lower().strip()
            if query_lower in name_lower or any(word in name_lower for word in query_lower.split()):
                suggestions.append(contact)
        
        # Sort by name similarity
        if suggestions:
            import difflib
            contact_names = [c.name.lower().strip() for c in suggestions]
            sorted_matches = difflib.get_close_matches(query_lower, contact_names, n=max_results, cutoff=0.3)
            
            result = []
            for match in sorted_matches:
                for contact in suggestions:
                    if contact.name.lower().strip() == match and contact not in result:
                        result.append(contact)
                        break
            
            return result[:max_results]
        
        return []
    
    def clear_cache(self):
        """Clear the contacts cache to force reload"""
        self._contacts_cache = None


# Global instance
_contacts_service = None

def get_contacts_service() -> ContactsService:
    """Get the global contacts service instance"""
    global _contacts_service
    if _contacts_service is None:
        _contacts_service = ContactsService()
    return _contacts_service