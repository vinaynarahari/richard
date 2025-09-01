#!/usr/bin/env python3

import tempfile
import subprocess
from faster_whisper import WhisperModel

# Create test audio with speech
print("Creating test audio with speech...")
with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
    temp_path = temp_file.name

# Generate simple sine wave audio
cmd = [
    'ffmpeg', '-f', 'lavfi', 
    '-i', 'sine=frequency=440:duration=3',
    '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
    '-y', temp_path
]

try:
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"✅ Created test audio: {temp_path}")
except Exception as e:
    print(f"❌ Failed to create audio: {e}")
    exit(1)

# Test faster-whisper directly
print("Testing faster-whisper directly...")
try:
    model = WhisperModel("tiny", device="cpu")
    print("✅ Model loaded")
    
    segments, info = model.transcribe(temp_path, language="en")
    print(f"Language: {info.language}")
    
    text_parts = []
    for segment in segments:
        text_parts.append(segment.text)
        print(f"[{segment.start:.1f}s -> {segment.end:.1f}s] {segment.text}")
    
    full_text = " ".join(text_parts).strip()
    print(f"\nFull transcription: '{full_text}'")
    
    if full_text:
        print("✅ Faster-whisper is working!")
    else:
        print("⚠️ No transcription - audio might be too simple")
        
except Exception as e:
    print(f"❌ Faster-whisper failed: {e}")
    import traceback
    traceback.print_exc()

# Cleanup
import os
try:
    os.unlink(temp_path)
except:
    pass