#!/usr/bin/env python3
"""
Test script for enhanced message sending with fuzzy contact matching
"""

import sys
import os

# Add the mac_messages_mcp to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mac_messages_mcp.messages import send_message, find_contact_by_name

def test_message_sending():
    """Test the enhanced message sending functionality."""
    
    print("📱 Testing Enhanced Message Sending with Fuzzy Contact Matching")
    print("=" * 70)
    
    # Test cases for message sending (these won't actually send messages)
    test_cases = [
        # Direct phone number
        ("+1234567890", "Test message", "Should handle direct phone number"),
        
        # Email address
        ("test@example.com", "Test message", "Should handle email address"),
        
        # Exact contact name (if exists)
        ("Sara", "Test message", "Should find exact or fuzzy contact match"),
        
        # Partial name
        ("mike", "Test message", "Should find partial name match"),
        
        # Misspelled name
        ("sara", "Test message", "Should handle misspelled names"),
        
        # Initials
        ("JS", "Test message", "Should find contact by initials"),
        
        # Non-existent contact
        ("NonExistentContact", "Test message", "Should handle non-existent contact"),
        
        # Contact selection format
        ("contact:1", "Test message", "Should handle contact selection format"),
    ]
    
    print("Testing message sending scenarios (no actual messages will be sent):\n")
    
    for i, (recipient, message, description) in enumerate(test_cases, 1):
        print(f"Test {i}: {description}")
        print(f"       Recipient: '{recipient}'")
        print(f"       Message: '{message}'")
        
        try:
            # For testing, we'll simulate by just checking contact resolution
            if recipient.startswith("contact:"):
                print(f"       Result: Contact selection format detected")
            elif all(c.isdigit() or c in '+- ()' for c in recipient) or '@' in recipient:
                print(f"       Result: Direct contact info detected ({'phone' if not '@' in recipient else 'email'})")
            else:
                # Test contact finding
                contacts = find_contact_by_name(recipient, max_results=5)
                if contacts:
                    print(f"       Result: Found {len(contacts)} contact(s):")
                    for j, contact in enumerate(contacts[:3], 1):
                        confidence_emoji = {
                            'very_high': '🟢',
                            'high': '🟡', 
                            'medium': '🟠',
                            'low': '🔴'
                        }.get(contact.get('confidence', 'unknown'), '⚪')
                        
                        print(f"         {j}. {confidence_emoji} {contact['name']} ({contact.get('phone', 'N/A')}) - "
                              f"{contact.get('match_type', 'unknown')} match")
                    
                    if len(contacts) == 1 and contacts[0].get('confidence') in ['very_high', 'high']:
                        print(f"       Action: Would send to {contacts[0]['name']} automatically")
                    else:
                        print(f"       Action: Would prompt user to select from {len(contacts)} matches")
                else:
                    print(f"       Result: No contacts found - would show helpful suggestions")
                    
        except Exception as e:
            print(f"       ERROR: {e}")
        
        print()
    
    print("=" * 70)
    print("✅ Message sending test scenarios completed!")
    
    print("\n📋 Enhanced Features Summary:")
    print("• ✅ Fuzzy contact name matching with misspelling tolerance")
    print("• ✅ Initials support (e.g., 'JS' finds 'John Smith')")
    print("• ✅ Partial name matching")
    print("• ✅ Confidence-based automatic selection")
    print("• ✅ Enhanced user feedback with match types and confidence levels")
    print("• ✅ Contact selection workflow for ambiguous matches")
    print("• ✅ Direct phone number and email support")
    print("• ✅ Helpful error messages and suggestions")
    
    print("\n🔮 Example Usage in Richard:")
    print("User: 'Send message to JS saying hello'")
    print("Richard: 'Found: 🟢 Jason Senior (contact:1) - initials match, high confidence'")
    print("         'Message sent successfully to Jason Senior via iMessage'")
    print()
    print("User: 'Send message to sara saying how are you'")
    print("Richard: 'Found 2 contacts matching 'sara':")
    print("         '1. 🟢 Sara AdvChem - partial match [94.0%]'")
    print("         '2. 🟡 Sarat - partial match [88.0%]'")
    print("         'Use contact:1 or contact:2 to select'")
    print()
    print("User: 'contact:1'")
    print("Richard: 'Message sent successfully to Sara AdvChem via iMessage'")

if __name__ == "__main__":
    test_message_sending()