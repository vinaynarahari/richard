#!/usr/bin/env python3
"""
Test script for the new fast STT service
"""

import asyncio
import os
import sys
import tempfile
import subprocess
from pathlib import Path

# Add the orchestrator app to the path
sys.path.insert(0, str(Path(__file__).parent / "services" / "orchestrator"))

async def test_fast_stt():
    """Test the fast STT service"""
    
    print("🎤 Testing Fast Speech-to-Text Service")
    print("=" * 50)
    
    # Initialize STT service
    try:
        from app.stt.local_stt import LocalSTTService
        stt = LocalSTTService()
    except ImportError as e:
        print(f"❌ Failed to import STT service: {e}")
        return
    
    # Check available methods
    print("🔍 Checking available STT methods:")
    print(f"   OpenAI API Key: {'✅' if stt.openai_api_key else '❌'}")
    print(f"   Groq API Key: {'✅' if stt.groq_api_key else '❌'}")
    
    # Try to check for faster-whisper
    try:
        import faster_whisper
        print(f"   Faster-Whisper: ✅")
    except ImportError:
        print(f"   Faster-Whisper: ❌ (run ./install_fast_stt.sh)")
    
    # Create a simple test audio file (silence)
    print("\n🎵 Creating test audio file...")
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
        temp_path = temp_file.name
    
    # Generate 2 seconds of silence as test audio
    cmd = [
        'ffmpeg', '-f', 'lavfi', '-i', 'anullsrc=r=16000:cl=mono', 
        '-t', '2', '-y', temp_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"   Created: {temp_path}")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Failed to create test audio: {e}")
        return
    except FileNotFoundError:
        print("   ❌ FFmpeg not found. Run ./install_fast_stt.sh first")
        return
    
    # Test transcription
    print("\n🔍 Testing transcription...")
    try:
        result = await stt.transcribe(temp_path, language="en")
        
        print(f"   Success: {result['success']}")
        print(f"   Method: {result['method']}")
        print(f"   Confidence: {result['confidence']}")
        print(f"   Text: '{result['text']}'")
        
        if result['success']:
            print("✅ STT service is working!")
        else:
            print(f"❌ STT failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ STT test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        try:
            os.unlink(temp_path)
        except:
            pass
    
    print("\n" + "=" * 50)
    print("📋 Setup Instructions:")
    print("1. Install dependencies: ./install_fast_stt.sh")
    print("2. Get Groq API key (free): https://console.groq.com")
    print("3. Set environment: export GROQ_API_KEY='your-key'")
    print("4. Restart the voice service")

if __name__ == "__main__":
    asyncio.run(test_fast_stt())