#!/usr/bin/env python3
"""
Test the new STT service
"""

import asyncio
import sys
import os
import tempfile
import subprocess

# Add path for imports
sys.path.append('services/orchestrator')

async def test_stt_service():
    """Test the STT service with a real audio file"""
    print("🎤 Testing Local STT Service")
    print("=" * 50)
    
    # Create a test audio file
    print("1. Creating test audio file...")
    temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_audio.close()
    
    # Generate a 3-second sine wave at 440Hz (A note)
    cmd = [
        'ffmpeg', '-f', 'lavfi', 
        '-i', 'sine=frequency=440:duration=3',
        '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
        '-y', temp_audio.name
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"   ✅ Created test audio: {temp_audio.name}")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Failed to create audio: {e}")
        return
    
    # Test the STT service
    print("\n2. Testing STT service...")
    try:
        from app.stt.local_stt import get_stt_service
        
        stt_service = get_stt_service()
        print(f"   📍 STT service initialized")
        print(f"   📍 Whisper.cpp: {stt_service.whisper_cpp_path}")
        print(f"   📍 Whisper model: {stt_service.model_path}")
        
        # Test transcription
        print("   🔄 Running transcription...")
        result = await stt_service.transcribe(temp_audio.name)
        
        print(f"\n3. STT Results:")
        print(f"   Success: {result.get('success', False)}")
        print(f"   Text: '{result.get('text', '')}'")
        print(f"   Method: {result.get('method', 'unknown')}")
        print(f"   Confidence: {result.get('confidence', 0.0)}")
        
        if result.get('error'):
            print(f"   Error: {result['error']}")
        
    except Exception as e:
        print(f"   ❌ STT service error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test via API endpoint
    print(f"\n4. Testing via API endpoint...")
    try:
        import httpx
        
        # Check if server is running
        async with httpx.AsyncClient() as client:
            try:
                health_response = await client.get("http://127.0.0.1:5273/health", timeout=5)
                health_response.raise_for_status()
                print("   ✅ Server is running")
                
                # Test transcription endpoint
                with open(temp_audio.name, 'rb') as f:
                    files = {"file": ("test.wav", f, "audio/wav")}
                    response = await client.post(
                        "http://127.0.0.1:5273/voice/transcribe",
                        files=files,
                        timeout=30
                    )
                    response.raise_for_status()
                    
                    api_result = response.json()
                    print(f"   API Result: {api_result}")
                    
            except httpx.ConnectError:
                print("   ❌ Server not running - start with: uvicorn app.main:app --reload --host 127.0.0.1 --port 5273")
            except Exception as e:
                print(f"   ❌ API test failed: {e}")
                
    except ImportError:
        print("   ⚠️  httpx not available for API testing")
    
    # Cleanup
    try:
        os.unlink(temp_audio.name)
        print(f"\n5. Cleaned up test file")
    except Exception:
        pass
    
    print(f"\n" + "=" * 50)
    print("🎉 STT Service Test Complete!")
    
    # Show setup instructions
    print(f"\n💡 To improve STT performance:")
    print("   1. Run: python services/orchestrator/setup_stt.py")
    print("   2. Install whisper.cpp: brew install whisper-cpp")
    print("   3. Install SpeechRecognition: pip install SpeechRecognition")
    print("   4. Install PyObjC: pip install pyobjc-framework-Speech")

if __name__ == "__main__":
    asyncio.run(test_stt_service())