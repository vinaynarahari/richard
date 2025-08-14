"""
Local Speech-to-Text service using multiple approaches
"""

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class LocalSTTService:
    """Local Speech-to-Text service with multiple backend options"""
    
    def __init__(self):
        self.whisper_cpp_path = self._find_whisper_cpp()
        self.model_path = self._find_whisper_model()
        
    def _find_whisper_cpp(self) -> Optional[str]:
        """Stubbed: we are not using whisper.cpp right now"""
        return None
    
    def _find_whisper_model(self) -> Optional[str]:
        """Stubbed: we are not using whisper.cpp right now"""
        return None
    
    async def transcribe_with_whisper_cpp(self, audio_path: str) -> Optional[str]:
        """Transcribe using local whisper.cpp"""
        if not self.whisper_cpp_path or not self.model_path:
            return None
        # Disabled path
        return None
    
    async def transcribe_with_macos_speech(self, audio_path: str) -> Optional[str]:
        """Transcribe using macOS Speech Framework via AppleScript"""
        try:
            # Convert to proper format
            wav_path = await self._convert_to_wav(audio_path)
            if not wav_path:
                return None
            
            # Use AppleScript to access Speech Recognition
            applescript = f'''
            tell application "System Events"
                try
                    set audioFile to POSIX file "{wav_path}"
                    -- Note: This is a placeholder - actual Speech Framework access
                    -- would require a Swift/ObjC bridge or using dictation services
                    return "macOS speech recognition placeholder"
                on error
                    return ""
                end try
            end tell
            '''
            
            result = await asyncio.create_subprocess_exec(
                'osascript', '-e', applescript,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                text = stdout.decode().strip()
                if text and "placeholder" not in text.lower():
                    if wav_path != audio_path:
                        os.unlink(wav_path)
                    return text
                    
        except Exception as e:
            logger.error(f"macOS speech recognition error: {e}")
        
        return None
    
    async def transcribe_with_python_speech_recognition(self, audio_path: str) -> Optional[str]:
        """Transcribe using Python speech_recognition library"""
        try:
            # Try to import speech_recognition
            import speech_recognition as sr
            
            # Convert to WAV format
            wav_path = await self._convert_to_wav(audio_path)
            if not wav_path:
                return None
            
            recognizer = sr.Recognizer()
            
            # Load audio file
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            
            # Try different recognition engines
            engines = [
                ('google', lambda: recognizer.recognize_google(audio_data)),
                ('sphinx', lambda: recognizer.recognize_sphinx(audio_data)),
            ]
            
            for engine_name, recognize_func in engines:
                try:
                    text = recognize_func()
                    if text:
                        logger.info(f"Transcription successful with {engine_name}")
                        if wav_path != audio_path:
                            os.unlink(wav_path)
                        return text.strip()
                except Exception as e:
                    logger.debug(f"{engine_name} recognition failed: {e}")
                    continue
                    
        except ImportError:
            logger.warning("speech_recognition library not available")
        except Exception as e:
            logger.error(f"Python speech recognition error: {e}")
        
        return None
    
    async def _convert_to_wav(self, audio_path: str) -> Optional[str]:
        """Convert audio file to WAV format suitable for STT"""
        try:
            # Check if already proper WAV
            if audio_path.endswith('.wav'):
                # Verify it's the right format
                result = await asyncio.create_subprocess_exec(
                    'ffprobe', '-i', audio_path, '-show_entries', 
                    'stream=sample_rate,channels,codec_name', 
                    '-v', 'quiet', '-of', 'csv=p=0',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, _ = await result.communicate()
                info = stdout.decode().strip().split(',')
                
                if len(info) >= 3:
                    codec, channels, sample_rate = info[0], info[1], info[2]
                    if codec == 'pcm_s16le' and channels == '1' and sample_rate == '16000':
                        return audio_path  # Already correct format
            
            # Convert to proper format
            temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_wav.close()
            
            conversion_cmd = [
                'ffmpeg', '-i', audio_path,
                '-ar', '16000',
                '-ac', '1', 
                '-c:a', 'pcm_s16le',
                '-f', 'wav',
                '-y', temp_wav.name
            ]
            
            result = await asyncio.create_subprocess_exec(
                *conversion_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await result.communicate()
            
            if result.returncode == 0:
                return temp_wav.name
            else:
                logger.error(f"Audio conversion failed: {stderr.decode()}")
                os.unlink(temp_wav.name)
                
        except Exception as e:
            logger.error(f"Audio conversion error: {e}")
        
        return None
    
    async def transcribe(self, audio_path: str, language: str = "en") -> Dict[str, Any]:
        """
        Transcribe audio using the best available method
        Returns dict with 'text', 'confidence', 'method', 'language'
        """
        prefer_whisper = os.getenv("PREFER_WHISPER_CPP", "false").lower() in ("1", "true", "yes")
        if prefer_whisper:
            methods = [
                ("whisper.cpp", self.transcribe_with_whisper_cpp),
                ("python_sr", self.transcribe_with_python_speech_recognition),
                ("macos_speech", self.transcribe_with_macos_speech),
            ]
        else:
            methods = [
                ("python_sr", self.transcribe_with_python_speech_recognition),
                ("whisper.cpp", self.transcribe_with_whisper_cpp),
                ("macos_speech", self.transcribe_with_macos_speech),
            ]
        
        for method_name, method_func in methods:
            try:
                logger.info(f"Trying transcription with {method_name}")
                text = await method_func(audio_path)
                
                if text and text.strip():
                    return {
                        "text": text.strip(),
                        "confidence": 0.9 if method_name == "whisper.cpp" else 0.85,
                        "method": method_name,
                        "language": language,
                        "success": True
                    }
                    
            except Exception as e:
                logger.error(f"Method {method_name} failed: {e}")
                continue
        
        # All methods failed
        return {
            "text": "",
            "confidence": 0.0,
            "method": "none",
            "language": language,
            "success": False,
            "error": "All transcription methods failed"
        }


# Singleton instance
_stt_service = None

def get_stt_service() -> LocalSTTService:
    """Get singleton STT service instance"""
    global _stt_service
    if _stt_service is None:
        _stt_service = LocalSTTService()
    return _stt_service