#!/usr/bin/env python3
"""
Setup script for Speech-to-Text dependencies
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"📦 {description}")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"   ✅ Success: {description}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Failed: {e.stderr}")
        return False

def check_dependency(cmd, name):
    """Check if a dependency is available"""
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"   ✅ {name} is available")
        return True
    except subprocess.CalledProcessError:
        print(f"   ❌ {name} is not available")
        return False

def main():
    print("🎤 Setting up Speech-to-Text Dependencies")
    print("=" * 50)
    
    # Check existing dependencies
    print("\n1. Checking existing dependencies:")
    ffmpeg_ok = check_dependency("ffmpeg -version", "FFmpeg")
    brew_ok = check_dependency("brew --version", "Homebrew")
    
    # Install Python dependencies
    print("\n2. Installing Python packages:")
    python_packages = [
        "SpeechRecognition",
        "pyobjc-framework-Speech", 
        "pyobjc-framework-AVFoundation",
        "pydub"
    ]
    
    for package in python_packages:
        success = run_command(f"pip install {package}", f"Installing {package}")
        if not success:
            print(f"   ⚠️  {package} installation failed - continuing anyway")
    
    # Install system dependencies
    print("\n3. Installing system dependencies:")
    if brew_ok:
        if not ffmpeg_ok:
            run_command("brew install ffmpeg", "Installing FFmpeg via Homebrew")
        
        # Try to install whisper.cpp
        run_command("brew install whisper-cpp", "Installing whisper.cpp")
        
    else:
        print("   ⚠️  Homebrew not available - please install manually:")
        print("      - FFmpeg: https://ffmpeg.org/download.html")
        print("      - whisper.cpp: https://github.com/ggerganov/whisper.cpp")
    
    # Download Whisper model
    print("\n4. Setting up Whisper models:")
    whisper_dir = Path.home() / "whisper.cpp"
    models_dir = whisper_dir / "models"
    
    if whisper_dir.exists():
        print(f"   Found whisper.cpp directory at {whisper_dir}")
        
        if not models_dir.exists():
            models_dir.mkdir(parents=True, exist_ok=True)
        
        base_model = models_dir / "ggml-base.en.bin"
        if not base_model.exists():
            print("   📥 Downloading base English model...")
            download_cmd = f"""
            cd {whisper_dir} && ./models/download-ggml-model.sh base.en
            """
            run_command(download_cmd, "Downloading Whisper base.en model")
        else:
            print("   ✅ Whisper model already exists")
    else:
        print("   ⚠️  whisper.cpp not found - installing from source:")
        clone_cmd = f"""
        cd {Path.home()} && 
        git clone https://github.com/ggerganov/whisper.cpp.git &&
        cd whisper.cpp &&
        make &&
        ./models/download-ggml-model.sh base.en
        """
        run_command(clone_cmd, "Building whisper.cpp from source")
    
    print("\n5. Testing STT setup:")
    
    # Create test audio
    test_cmd = """
    ffmpeg -f lavfi -i "sine=frequency=440:duration=1" -ar 16000 -ac 1 test_stt.wav -y 2>/dev/null
    """
    
    if run_command(test_cmd, "Creating test audio file"):
        # Test STT service
        test_script = """
import sys
sys.path.append('.')
from app.stt.local_stt import get_stt_service
import asyncio

async def test():
    stt = get_stt_service()
    result = await stt.transcribe('test_stt.wav')
    print(f"STT Test Result: {result}")

asyncio.run(test())
        """
        
        with open("test_stt.py", "w") as f:
            f.write(test_script)
        
        print("   🧪 Testing STT service...")
        run_command("python test_stt.py", "Testing STT functionality")
        
        # Cleanup
        run_command("rm -f test_stt.wav test_stt.py", "Cleaning up test files")
    
    print("\n" + "=" * 50)
    print("🎉 STT Setup Complete!")
    print("\n💡 Available STT methods:")
    print("   • whisper.cpp (local, high quality)")
    print("   • Python SpeechRecognition (multiple engines)")
    print("   • macOS Speech Framework (native)")
    print("\n🚀 Your voice transcription system is ready!")

if __name__ == "__main__":
    main()