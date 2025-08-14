#!/usr/bin/env python3
"""
Simple command-line voice interface for Richard
Usage: python voice_cli.py
"""

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path

import httpx

RICHARD_URL = "http://127.0.0.1:5273"


async def record_audio() -> str:
    """Record audio using macOS built-in tools"""
    print("🎤 Recording... (Press Enter when done speaking)")
    
    # Create temporary file for recording
    temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_path = temp_file.name
    temp_file.close()
    
    try:
        # Start recording in background using macOS rec command
        # Alternative: use QuickTime or other system recording
        print("Say your command now...")
        
        # Use afrecord (macOS built-in) to record audio
        process = subprocess.Popen([
            'afrecord',
            '--file-format', 'WAVE',
            '--data-format', '1', # PCM
            '--sample-rate', '16000',
            '--num-channels', '1',
            '--duration', '10',  # 10 second max
            temp_path
        ])
        
        # Wait for user to press enter or timeout
        input("Press Enter when done speaking...")
        
        # Terminate recording
        process.terminate()
        process.wait()
        
        return temp_path
        
    except Exception as e:
        print(f"❌ Recording failed: {e}")
        try:
            Path(temp_path).unlink()
        except Exception:
            pass
        return ""


async def transcribe_audio(audio_file: str) -> str:
    """Transcribe audio using Richard's speech recognition endpoint"""
    try:
        async with httpx.AsyncClient() as client:
            with open(audio_file, 'rb') as f:
                files = {"file": ("audio.wav", f, "audio/wav")}
                
                response = await client.post(
                    f"{RICHARD_URL}/voice/transcribe",
                    files=files,
                    timeout=60.0
                )
                response.raise_for_status()
                
                result = response.json()
                text = result.get("text", "").strip()
                
                # Check if transcription failed
                if "transcription not available" in text.lower():
                    print("⚠️ Audio transcription not available - falling back to text input")
                    text = input("🎤 Please type what you said: ").strip()
                else:
                    print(f"🗣️ You said: '{text}'")
                
                return text
                
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        print("⚠️ Falling back to text input")
        return input("🎤 Please type what you said: ").strip()


async def send_command_to_richard(text: str) -> None:
    """Send command to Richard via chat endpoint"""
    try:
        # Check if it's a wake word
        if "hey richard" in text.lower() or "hi richard" in text.lower():
            # Extract the command after wake word
            parts = text.lower().split("richard", 1)
            if len(parts) > 1:
                command = parts[1].strip()
                if command:
                    text = command
                else:
                    print("👋 Hello! What can I help you with?")
                    return
            else:
                print("👋 Hello! What can I help you with?")
                return
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{RICHARD_URL}/llm/chat",
                json={
                    "messages": [{"role": "user", "content": text}],
                    "mode": "quick",
                    "temperature": 0.3,
                    "max_tokens": 256
                },
                timeout=30.0
            )
            response.raise_for_status()
            
            # Stream the response
            print("🤖 Richard:", end=" ", flush=True)
            response_text = ""
            
            # Parse SSE response
            for line in response.text.split('\n'):
                if line.startswith('data: '):
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "token" and data.get("content"):
                            content = data["content"]
                            print(content, end="", flush=True)
                            response_text += content
                    except json.JSONDecodeError:
                        pass
            
            print()  # New line after response
            
            # Speak the response using macOS say
            if response_text.strip():
                clean_response = response_text.strip()
                # Remove function call syntax
                import re
                clean_response = re.sub(r'CALL_\w+\([^)]+\)', '', clean_response).strip()
                
                if clean_response:
                    subprocess.run(['say', '-r', '220', clean_response], check=False)
                    
    except Exception as e:
        print(f"❌ Failed to send command: {e}")


async def simple_voice_mode():
    """Simple text input mode for testing"""
    print("💬 Simple Voice Mode (Text Input)")
    print("Type 'quit' to exit")
    
    while True:
        try:
            text = input("\n🎤 You: ").strip()
            if text.lower() in ['quit', 'exit', 'bye']:
                break
            
            if text:
                await send_command_to_richard(text)
                
        except KeyboardInterrupt:
            break


async def voice_recording_mode():
    """Voice recording mode"""
    print("🎤 Voice Recording Mode")
    print("Press Enter to start recording, then Enter again when done")
    print("Type 'quit' to exit")
    
    while True:
        try:
            choice = input("\nPress Enter to record (or 'quit' to exit): ").strip()
            if choice.lower() in ['quit', 'exit']:
                break
            
            # Record audio
            audio_file = await record_audio()
            if not audio_file:
                continue
            
            try:
                # Transcribe
                text = await transcribe_audio(audio_file)
                if text:
                    # Send to Richard
                    await send_command_to_richard(text)
                    
            finally:
                # Clean up audio file
                try:
                    Path(audio_file).unlink()
                except Exception:
                    pass
                    
        except KeyboardInterrupt:
            break


async def main():
    """Main function"""
    print("🎤 Richard Voice CLI")
    print("=" * 50)
    
    # Check if Richard is running
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{RICHARD_URL}/health", timeout=5.0)
            response.raise_for_status()
            print("✅ Richard server is running")
    except Exception:
        print("❌ Richard server is not running!")
        print("Start it with: uvicorn app.main:app --app-dir services/orchestrator --reload --host 127.0.0.1 --port 5273")
        return
    
    while True:
        print("\nChoose mode:")
        print("1. Text input mode (type commands)")
        print("2. Voice recording mode (record audio)")
        print("3. Exit")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "1":
            await simple_voice_mode()
        elif choice == "2":
            await voice_recording_mode()
        elif choice == "3":
            print("👋 Goodbye!")
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