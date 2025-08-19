#!/usr/bin/env python3
"""
Test script to check Messages database access
"""

import sqlite3
import os
from pathlib import Path

def test_messages_db_access():
    """Test if we can access the Messages database"""
    
    # Standard Messages database path
    messages_db_path = Path.home() / "Library" / "Messages" / "chat.db"
    
    print(f"Testing Messages database access...")
    print(f"Database path: {messages_db_path}")
    print(f"Database exists: {messages_db_path.exists()}")
    
    if not messages_db_path.exists():
        print("❌ Messages database not found!")
        return False
        
    try:
        # Try to connect and read from the database
        conn = sqlite3.connect(str(messages_db_path))
        cursor = conn.cursor()
        
        # Try a simple query
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"✅ Successfully connected to Messages database")
        print(f"Found {len(tables)} tables")
        
        # Try to get recent messages count - Messages uses a different timestamp format
        # Messages database uses Core Data timestamp (seconds since 2001-01-01)
        cursor.execute("SELECT COUNT(*) FROM message WHERE date > (strftime('%s', 'now') - strftime('%s', '2001-01-01') - 86400) * 1000000000;")
        recent_count = cursor.fetchone()[0]
        print(f"Recent messages (last 24h): {recent_count}")
        
        # Let's also check total message count and recent timestamp format
        cursor.execute("SELECT COUNT(*) FROM message;")
        total_count = cursor.fetchone()[0]
        print(f"Total messages in database: {total_count}")
        
        # Check the most recent message timestamp to understand the format
        cursor.execute("SELECT date, text FROM message ORDER BY date DESC LIMIT 1;")
        latest = cursor.fetchone()
        if latest:
            print(f"Latest message timestamp: {latest[0]}")
            print(f"Latest message text: {latest[1][:50] if latest[1] else 'No text'}...")
        
        conn.close()
        return True
        
    except sqlite3.OperationalError as e:
        print(f"❌ Database access error: {e}")
        print("This usually means Full Disk Access permission is needed")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    test_messages_db_access()

