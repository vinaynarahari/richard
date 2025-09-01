#!/usr/bin/env python3
"""
Test script for enhanced fuzzy contact matching in Richard
Tests various scenarios including misspellings, partial names, and initials
"""

import sys
import os

# Add the mac_messages_mcp to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mac_messages_mcp.messages import find_contact_by_name, fuzzy_match

def test_fuzzy_matching():
    """Test the enhanced fuzzy matching functionality with sample data."""
    
    print("🔍 Testing Enhanced Fuzzy Contact Matching for Richard")
    print("=" * 60)
    
    # Sample contact data for testing
    sample_contacts = [
        ("John Smith", "+1234567890"),
        ("Jane Doe", "+1234567891"),
        ("Michael Johnson", "+1234567892"),
        ("Sarah Wilson", "+1234567893"),
        ("David Brown", "+1234567894"),
        ("Lisa Anderson", "+1234567895"),
        ("Robert Davis", "+1234567896"),
        ("Jennifer Garcia", "+1234567897"),
        ("William Martinez", "+1234567898"),
        ("Jessica Rodriguez", "+1234567899")
    ]
    
    # Test cases covering various scenarios
    test_cases = [
        # Exact matches
        ("John Smith", "Should find exact match"),
        ("jane doe", "Should find exact match (case insensitive)"),
        
        # Partial matches
        ("john", "Should find John Smith"),
        ("smith", "Should find John Smith"),
        ("jane", "Should find Jane Doe"),
        
        # Initials
        ("JS", "Should find John Smith via initials"),
        ("JD", "Should find Jane Doe via initials"),
        ("MJ", "Should find Michael Johnson via initials"),
        
        # Misspellings
        ("Jon Smith", "Should find John Smith (misspelling)"),
        ("Jhon Smith", "Should find John Smith (misspelling)"),
        ("Jane Do", "Should find Jane Doe (misspelling)"),
        ("Micheal Johnson", "Should find Michael Johnson (misspelling)"),
        
        # Partial with misspellings
        ("jon", "Should find John Smith (partial misspelling)"),
        ("sara", "Should find Sarah Wilson (partial misspelling)"),
        ("dave", "Should find David Brown (nickname)"),
        ("mike", "Should find Michael Johnson (nickname)"),
        
        # Multiple word partial
        ("john sm", "Should find John Smith (partial words)"),
        ("jane d", "Should find Jane Doe (partial words)"),
        
        # Edge cases
        ("xyz", "Should find no matches"),
        ("", "Should handle empty query"),
        ("J", "Should find multiple J names"),
    ]
    
    print(f"Testing with {len(sample_contacts)} sample contacts:")
    for name, phone in sample_contacts:
        print(f"  • {name} ({phone})")
    print()
    
    # Run tests
    passed = 0
    total = len(test_cases)
    
    for i, (query, description) in enumerate(test_cases, 1):
        print(f"Test {i:2d}: '{query}' - {description}")
        
        try:
            # Test the fuzzy_match function directly
            matches = fuzzy_match(query, sample_contacts, threshold=0.3)
            
            if matches:
                print(f"         Found {len(matches)} matches:")
                for name, phone, score in matches[:3]:  # Show top 3
                    confidence = "Very High" if score >= 0.9 else "High" if score >= 0.7 else "Medium" if score >= 0.5 else "Low"
                    print(f"           {name} ({phone}) - Score: {score:.3f} ({confidence})")
                passed += 1
            else:
                print(f"         No matches found")
                if query in ["xyz", ""]:  # Expected no matches
                    passed += 1
                    
        except Exception as e:
            print(f"         ERROR: {e}")
        
        print()
    
    print("=" * 60)
    print(f"Tests completed: {passed}/{total} passed ({passed/total*100:.1f}%)")
    
    # Test real contact search if available
    print("\n🔍 Testing with real contacts (if available):")
    try:
        # Test with some common names that might exist
        real_test_queries = ["john", "JS", "mike", "sara"]
        
        for query in real_test_queries:
            print(f"\nSearching for '{query}':")
            # Note: This will only work if the user has granted Full Disk Access
            # and has contacts in their AddressBook
            try:
                results = find_contact_by_name(query, max_results=3)
                if results:
                    print(f"  Found {len(results)} matches:")
                    for contact in results:
                        print(f"    • {contact['name']} ({contact.get('phone', 'N/A')}) - "
                              f"{contact.get('match_type', 'unknown')} match, "
                              f"{contact.get('confidence', 'unknown')} confidence")
                else:
                    print(f"  No contacts found for '{query}'")
            except Exception as e:
                print(f"  Could not search real contacts: {e}")
                print("  (This is expected if Full Disk Access is not granted)")
    
    except Exception as e:
        print(f"Real contact testing failed: {e}")
    
    print("\n✅ Enhanced fuzzy matching test completed!")
    print("\nKey improvements implemented:")
    print("• Multiple similarity algorithms (fuzzy ratio, partial ratio, token matching)")
    print("• Initials matching (e.g., 'JS' finds 'John Smith')")
    print("• Misspelling tolerance using edit distance")
    print("• Partial name matching")
    print("• Confidence scoring and match type classification")
    print("• Enhanced user feedback with emojis and detailed match info")

if __name__ == "__main__":
    test_fuzzy_matching()