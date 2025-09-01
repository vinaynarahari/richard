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
import httpx
import json

logger = logging.getLogger(__name__)


class LocalSTTService:
    """Local Speech-to-Text service with multiple backend options"""
    
    def __init__(self):
        self.whisper_cpp_path = self._find_whisper_cpp()
        self.model_path = self._find_whisper_model()
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        
    def _find_whisper_cpp(self) -> Optional[str]:
        """Stubbed: we are not using whisper.cpp right now"""
        return None
    
    def _find_whisper_model(self) -> Optional[str]:
        """Stubbed: we are not using whisper.cpp right now"""
        return None
    
    async def transcribe_with_openai_whisper(self, audio_path: str, language: str = "en") -> Optional[str]:
        """Transcribe using OpenAI Whisper API - fastest and most accurate"""
        if not self.openai_api_key:
            logger.warning("OpenAI API key not available")
            return None
            
        try:
            # Convert to proper format for OpenAI
            wav_path = await self._convert_to_wav(audio_path)
            if not wav_path:
                logger.error("Failed to convert audio for OpenAI Whisper")
                return None
            
            # Prepare the file for upload
            with open(wav_path, 'rb') as audio_file:
                files = {
                    'file': (os.path.basename(wav_path), audio_file, 'audio/wav'),
                    'model': (None, 'whisper-1'),
                    'language': (None, language),
                    'response_format': (None, 'text')
                }
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.openai_api_key}"},
                        files=files
                    )
            
            # Clean up temp file if we created one
            if wav_path != audio_path:
                os.unlink(wav_path)
            
            if response.status_code == 200:
                text = response.text.strip()
                if text:
                    logger.info(f"OpenAI Whisper transcription successful: {text[:50]}...")
                    return text
            else:
                logger.error(f"OpenAI Whisper API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"OpenAI Whisper transcription error: {e}")
        
        return None
    
    async def transcribe_with_groq_whisper(self, audio_path: str, language: str = "en") -> Optional[str]:
        """Transcribe using Groq Whisper API - very fast alternative"""
        if not self.groq_api_key:
            logger.warning("Groq API key not available")
            return None
            
        try:
            # Convert to proper format for Groq
            wav_path = await self._convert_to_wav(audio_path)
            if not wav_path:
                logger.error("Failed to convert audio for Groq Whisper")
                return None
            
            # Prepare the file for upload
            with open(wav_path, 'rb') as audio_file:
                files = {
                    'file': (os.path.basename(wav_path), audio_file, 'audio/wav'),
                    'model': (None, 'whisper-large-v3'),
                    'language': (None, language),
                    'response_format': (None, 'text')
                }
                
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.groq_api_key}"},
                        files=files
                    )
            
            # Clean up temp file if we created one
            if wav_path != audio_path:
                os.unlink(wav_path)
            
            if response.status_code == 200:
                text = response.text.strip()
                if text:
                    logger.info(f"Groq Whisper transcription successful: {text[:50]}...")
                    return text
            else:
                logger.error(f"Groq Whisper API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Groq Whisper transcription error: {e}")
        
        return None
    
    async def transcribe_with_faster_whisper(self, audio_path: str, language: str = "en") -> Optional[str]:
        """Transcribe using faster-whisper (local, very fast)"""
        try:
            # Try to import faster-whisper
            from faster_whisper import WhisperModel
            
            # Use small model for speed, can be configured
            model_size = os.getenv("WHISPER_MODEL_SIZE", "small")
            device = "cpu"  # Can be "cuda" if GPU available
            
            print(f"[DEBUG STT] Starting transcription with faster-whisper")
            print(f"[DEBUG STT] Original audio path: {audio_path}")
            print(f"[DEBUG STT] Model size: {model_size}, Device: {device}")
            
            # Load model (cached after first use)
            if not hasattr(self, '_faster_whisper_model'):
                print(f"[DEBUG STT] Loading faster-whisper model: {model_size}")
                logger.info(f"Loading faster-whisper model: {model_size}")
                self._faster_whisper_model = WhisperModel(model_size, device=device)
            else:
                print(f"[DEBUG STT] Using cached faster-whisper model")
            
            # Convert to proper format
            print(f"[DEBUG STT] Converting audio to proper format...")
            wav_path = await self._convert_to_wav(audio_path)
            if not wav_path:
                print(f"[DEBUG STT] Audio conversion failed!")
                return None
            
            print(f"[DEBUG STT] Converted audio path: {wav_path}")
            
            # Check file size
            file_size = os.path.getsize(wav_path)
            print(f"[DEBUG STT] Audio file size: {file_size} bytes")
            
            print(f"[DEBUG STT] Starting transcription with settings:")
            print(f"[DEBUG STT]   Language: {language}")
            print(f"[DEBUG STT]   VAD filter: False")
            print(f"[DEBUG STT]   No speech threshold: 0.1")
            
            # Transcribe with very sensitive settings to catch all speech
            segments, info = self._faster_whisper_model.transcribe(
                wav_path, 
                language=language,
                beam_size=1,
                best_of=1,
                vad_filter=False,  # Completely disable voice activity detection
                temperature=0.0,
                compression_ratio_threshold=4.0,  # More lenient
                log_prob_threshold=-2.0,  # More lenient
                no_speech_threshold=0.1,  # Much more sensitive to speech
                condition_on_previous_text=False,
                word_timestamps=False,
                initial_prompt=None,
            )
            
            print(f"[DEBUG STT] Transcription complete. Language detected: {info.language}")
            print(f"[DEBUG STT] Language probability: {getattr(info, 'language_probability', 'unknown')}")
            print(f"[DEBUG STT] Duration: {getattr(info, 'duration', 'unknown')} seconds")
            
            # Collect all segments
            text_parts = []
            segment_count = 0
            
            print(f"[DEBUG STT] Processing segments...")
            for segment in segments:
                segment_count += 1
                print(f"[DEBUG STT] Segment {segment_count}: [{segment.start:.1f}s-{segment.end:.1f}s] '{segment.text}'")
                print(f"[DEBUG STT]   Avg log prob: {getattr(segment, 'avg_logprob', 'unknown')}")
                print(f"[DEBUG STT]   No speech prob: {getattr(segment, 'no_speech_prob', 'unknown')}")
                logger.info(f"Segment {segment_count}: [{segment.start:.1f}s-{segment.end:.1f}s] '{segment.text}'")
                text_parts.append(segment.text)
            
            print(f"[DEBUG STT] Total segments processed: {segment_count}")
            logger.info(f"Faster-whisper processed {segment_count} segments from audio")
            
            # Clean up temp file if we created one
            if wav_path != audio_path:
                os.unlink(wav_path)
            
            if text_parts:
                result = " ".join(text_parts).strip()
                print(f"[DEBUG STT] Final transcription result: '{result}'")
                logger.info(f"Faster-whisper transcription successful: '{result}'")
                return result
            else:
                print(f"[DEBUG STT] No speech segments found!")
                logger.warning("Faster-whisper found no speech segments")
                
        except ImportError:
            logger.warning("faster-whisper not available. Install with: pip install faster-whisper")
        except Exception as e:
            logger.error(f"Faster-whisper transcription error: {e}")
        
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
        # Priority order: Local methods first (no API keys needed)
        methods = [
            ("faster_whisper", lambda path: self.transcribe_with_faster_whisper(path, language)),
            ("python_sr", self.transcribe_with_python_speech_recognition),
            ("whisper.cpp", self.transcribe_with_whisper_cpp),
            ("macos_speech", self.transcribe_with_macos_speech),
        ]
        
        # Environment override for preferred method (keeping it simple)
        preferred_method = os.getenv("STT_PREFERRED_METHOD", "").lower()
        if preferred_method == "python_sr":
            methods = [
                ("python_sr", self.transcribe_with_python_speech_recognition),
                ("faster_whisper", lambda path: self.transcribe_with_faster_whisper(path, language)),
            ]
        
        for method_name, method_func in methods:
            try:
                logger.info(f"Trying transcription with {method_name}")
                text = await method_func(audio_path)
                
                if text and text.strip():
                    # Higher confidence for API-based Whisper models
                    confidence = 0.95 if method_name.endswith("_whisper") else 0.85
                    if method_name == "whisper.cpp":
                        confidence = 0.9
                    
                    return {
                        "text": text.strip(),
                        "confidence": confidence,
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