#!/usr/bin/env python3
"""
Simple voice test client for Richard
Usage: python voice_test.py
"""

import asyncio
import json
from typing import Dict, Any

import httpx

RICHARD_URL = "http://127.0.0.1:5273"


async def start_voice_assistant():
    """Start the voice assistant"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{RICHARD_URL}/voice/start", json={
                "wake_word": "hey richard",
                "enable_tts": True,
                "voice_speed": 1.2
            })
            response.raise_for_status()
            result = response.json()
            print(f"✅ Voice assistant started: {result['message']}")
            return True
        except Exception as e:
            print(f"❌ Failed to start voice assistant: {e}")
            return False


async def stop_voice_assistant():
    """Stop the voice assistant"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{RICHARD_URL}/voice/stop")
            response.raise_for_status()
            result = response.json()
            print(f"✅ Voice assistant stopped: {result['message']}")
            return True
        except Exception as e:
            print(f"❌ Failed to stop voice assistant: {e}")
            return False


async def get_voice_status():
    """Get voice assistant status"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{RICHARD_URL}/voice/status")
            response.raise_for_status()
            result = response.json()
            print(f"📊 Voice status: {json.dumps(result, indent=2)}")
            return result
        except Exception as e:
            print(f"❌ Failed to get status: {e}")
            return None


async def test_speak(text: str):
    """Test text-to-speech"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{RICHARD_URL}/voice/speak", json={
                "text": text
            })
            response.raise_for_status()
            result = response.json()
            print(f"🗣️ Spoke: {result['text']}")
            return True
        except Exception as e:
            print(f"❌ Failed to speak: {e}")
            return False


async def main():
    """Main test function"""
    print("🎤 Richard Voice Test Client")
    print("=" * 50)
    
    while True:
        print("\nOptions:")
        print("1. Start voice assistant")
        print("2. Stop voice assistant")
        print("3. Get status")
        print("4. Test speak")
        print("5. Exit")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            success = await start_voice_assistant()
            if success:
                print("\n🎤 Voice assistant is now listening for 'Hey Richard'...")
                print("Try saying: 'Hey Richard, send a message to John'")
        elif choice == "2":
            await stop_voice_assistant()
        elif choice == "3":
            await get_voice_status()
        elif choice == "4":
            text = input("Enter text to speak: ").strip()
            if text:
                await test_speak(text)
        elif choice == "5":
            print("👋 Goodbye!")
            await stop_voice_assistant()
            break
        else:
            print("❌ Invalid choice")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")