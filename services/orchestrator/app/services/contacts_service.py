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
        """Get all contacts from macOS Contacts app with multiple fallback methods"""
        if self._contacts_cache is not None:
            return self._contacts_cache
        
        # Try multiple methods in order of preference
        contacts = []
        
        # Method 1: Try AddressBook database directly (fastest)
        contacts = await self._get_contacts_from_addressbook()
        if contacts:
            self._contacts_cache = contacts
            logger.info(f"Loaded {len(contacts)} contacts from AddressBook database")
            return contacts
        
        # Method 2: Try simplified AppleScript (faster)
        contacts = await self._get_contacts_simplified_applescript()
        if contacts:
            self._contacts_cache = contacts
            logger.info(f"Loaded {len(contacts)} contacts from simplified AppleScript")
            return contacts
        
        # Method 3: Try contacts command line tool
        contacts = await self._get_contacts_from_cli()
        if contacts:
            self._contacts_cache = contacts
            logger.info(f"Loaded {len(contacts)} contacts from CLI tool")
            return contacts
        
        # Method 4: Try original AppleScript with longer timeout
        contacts = await self._get_contacts_original_applescript()
        if contacts:
            self._contacts_cache = contacts
            logger.info(f"Loaded {len(contacts)} contacts from original AppleScript")
            return contacts
        
        logger.warning("All contact retrieval methods failed")
        return []
    
    async def _get_contacts_from_addressbook(self) -> List[Contact]:
        """Try to get contacts directly from AddressBook database"""
        try:
            import sqlite3
            import glob
            import os
            
            home_dir = os.path.expanduser("~")
            db_pattern = os.path.join(home_dir, "Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb")
            db_paths = glob.glob(db_pattern)
            
            contacts = []
            for db_path in db_paths:
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    query = """
                    SELECT DISTINCT
                        ZABCDRECORD.ZFIRSTNAME as first_name,
                        ZABCDRECORD.ZLASTNAME as last_name,
                        ZABCDPHONENUMBER.ZFULLNUMBER as phone
                    FROM ZABCDRECORD
                    LEFT JOIN ZABCDPHONENUMBER ON ZABCDRECORD.Z_PK = ZABCDPHONENUMBER.ZOWNER
                    WHERE ZABCDPHONENUMBER.ZFULLNUMBER IS NOT NULL
                    LIMIT 200
                    """
                    
                    cursor.execute(query)
                    results = cursor.fetchall()
                    
                    contact_dict = {}
                    for first_name, last_name, phone in results:
                        name = " ".join(filter(None, [first_name or "", last_name or ""])).strip()
                        if name and phone:
                            if name not in contact_dict:
                                contact_dict[name] = []
                            contact_dict[name].append(phone)
                    
                    for name, phones in contact_dict.items():
                        contacts.append(Contact(name, phones, []))
                    
                    conn.close()
                    
                except Exception as e:
                    logger.debug(f"Failed to read AddressBook database {db_path}: {e}")
                    continue
            
            return contacts
            
        except Exception as e:
            logger.debug(f"AddressBook database method failed: {e}")
            return []
    
    async def _get_contacts_simplified_applescript(self) -> List[Contact]:
        """Try simplified AppleScript that's faster"""
        try:
            applescript = '''
            set output to ""
            tell application "Contacts"
                repeat with person in people
                    try
                        set personName to name of person
                        set phoneList to ""
                        repeat with phone in phones of person
                            if phoneList is "" then
                                set phoneList to value of phone
                            else
                                set phoneList to phoneList & "|" & value of phone
                            end if
                        end repeat
                        if personName is not "" and phoneList is not "" then
                            if output is "" then
                                set output to personName & ":" & phoneList
                            else
                                set output to output & "\n" & personName & ":" & phoneList
                            end if
                        end if
                    end try
                end repeat
            end tell
            return output
            '''
            
            result = subprocess.run(
                ['osascript', '-e', applescript],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return self._parse_contact_output(result.stdout.strip())
            
        except Exception as e:
            logger.debug(f"Simplified AppleScript failed: {e}")
        
        return []
    
    async def _get_contacts_from_cli(self) -> List[Contact]:
        """Try using contacts command line tool if available"""
        try:
            # Try using the 'contacts' command if it exists
            result = subprocess.run(
                ['which', 'contacts'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # contacts command exists, try to use it
                result = subprocess.run(
                    ['contacts', '-H', '-f', '%fn %ln:%p'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    return self._parse_contact_output(result.stdout.strip())
            
        except Exception as e:
            logger.debug(f"CLI contacts tool failed: {e}")
        
        return []
    
    async def _get_contacts_original_applescript(self) -> List[Contact]:
        """Original AppleScript method with longer timeout"""
        try:
            applescript = '''
            set contactsList to ""
            set contactCount to 0
            tell application "Contacts"
                repeat with aPerson in people
                    set contactCount to contactCount + 1
                    if contactCount > 200 then exit repeat
                    
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
                timeout=30  # Longer timeout
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return self._parse_contact_output(result.stdout.strip())
                    
        except Exception as e:
            logger.debug(f"Original AppleScript failed: {e}")
        
        return []
    
    def _parse_contact_output(self, output: str) -> List[Contact]:
        """Parse contact output in Name:phone1|phone2 format"""
        contacts = []
        try:
            for line in output.split('\n'):
                if ':' in line:
                    name, phones_str = line.split(':', 1)
                    phones = [p.strip() for p in phones_str.split('|') if p.strip()]
                    
                    if name.strip() and phones:
                        contacts.append(Contact(name.strip(), phones, []))
        except Exception as e:
            logger.error(f"Failed to parse contact output: {e}")
        
        return contacts
    
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
        """Get contact suggestions with enhanced fuzzy matching"""
        contacts = await self.get_all_contacts()
        
        if not contacts:
            logger.warning("No contacts available for suggestions")
            return []
        
        if not query or not query.strip():
            return contacts[:max_results]  # Return first few contacts if no query
            
        query_lower = query.lower().strip()
        query_words = query_lower.split()
        
        scored_contacts = []
        
        for contact in contacts:
            name_lower = contact.name.lower().strip()
            name_words = name_lower.split()
            
            score = 0.0
            
            # Exact match
            if query_lower == name_lower:
                score = 1.0
            # Exact substring match
            elif query_lower in name_lower:
                score = 0.9 * (len(query_lower) / len(name_lower))
            # Word-based matching
            elif any(word in name_lower for word in query_words if len(word) > 2):
                matching_words = sum(1 for word in query_words if word in name_lower and len(word) > 2)
                score = 0.8 * (matching_words / len(query_words))
            # Initials matching
            elif len(query_lower) <= 4 and all(c.isalpha() for c in query_lower):
                initials = ''.join([word[0] for word in name_words if word])
                if query_lower == initials:
                    score = 0.7
                elif query_lower in initials:
                    score = 0.6
            # Fuzzy matching using difflib
            else:
                import difflib
                similarity = difflib.SequenceMatcher(None, query_lower, name_lower).ratio()
                if similarity > 0.4:  # Lower threshold for better recall
                    score = similarity * 0.7
            
            if score > 0.3:  # Minimum threshold
                scored_contacts.append((contact, score))
        
        # Sort by score descending
        scored_contacts.sort(key=lambda x: x[1], reverse=True)
        
        # Return top matches
        result = [contact for contact, score in scored_contacts[:max_results]]
        
        logger.info(f"Found {len(result)} contact suggestions for query '{query}'")
        return result
    
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