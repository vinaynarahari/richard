from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from ..llm.ollama_client import OllamaClient

# Simplified voice using system commands
VOICE_AVAILABLE = True  # Always available on macOS


class VoiceConfig(BaseModel):
    # Audio settings
    sample_rate: int = 16000
    chunk_size: int = 4096
    channels: int = 1
    wake_word: str = "hey richard"
    
    # Whisper settings
    whisper_model: str = "ZimaBlueAI/whisper-large-v3:latest"
    
    # Wake word detection
    wake_word_threshold: float = 0.6
    silence_duration: float = 2.0  # seconds of silence before processing
    max_recording_duration: float = 30.0  # max seconds to record
    
    # Response settings
    enable_tts: bool = True
    voice_speed: float = 1.0  # multiplier applied to base WPM
    voice_name: str = "Alex"  # default male voice on macOS (fallback)
    voice_rate_wpm: int = 180  # base words per minute (before multiplier)

    # TTS provider settings
    tts_provider: str = "auto"  # auto|elevenlabs|piper|say
    elevenlabs_voice_id: Optional[str] = None  # set via ELEVENLABS_VOICE_ID
    piper_model_path: Optional[str] = None      # set via PIPER_MODEL_PATH
    piper_bin: str = os.getenv("PIPER_BIN", "piper")


class VoiceEngine:
    """
    Advanced voice engine with wake word detection and TTS integration
    """
    
    def __init__(self, config: Optional[VoiceConfig] = None, ollama_client: Optional[OllamaClient] = None):
        self.config = config or VoiceConfig()
        self.ollama = ollama_client or OllamaClient()
        
        # State
        self.is_listening = False
        self.is_recording = False
        self.wake_word_detected = False
        
        # Callbacks
        self.on_wake_word: Optional[Callable] = None
        self.on_command_received: Optional[Callable[[str], Any]] = None
        self.on_response_ready: Optional[Callable[[str], Any]] = None
        
        print(f"[VoiceEngine] Initialized with provider={self.config.tts_provider}")
    
    async def initialize(self) -> None:
        print("[VoiceEngine] Voice engine initialized successfully")
    
    def start_listening(self) -> None:
        if self.is_listening:
            return
        self.is_listening = True
        print(f"[VoiceEngine] Voice system ready")
        print("Use the manual recording endpoint to capture voice commands")
    
    def stop_listening(self) -> None:
        self.is_listening = False
        print("[VoiceEngine] Voice system stopped")
    
    async def process_voice_command(self, text: str) -> None:
        if self.on_command_received:
            await self.on_command_received(text)
    
    async def transcribe_with_ollama(self, audio_file_path: str) -> Optional[str]:
        """Removed: no Ollama usage"""
        return None

    async def _tts_elevenlabs(self, text: str) -> Optional[Path]:
        api_key = os.getenv("ELEVENLABS_API_KEY")
        voice_id = self.config.elevenlabs_voice_id or os.getenv("ELEVENLABS_VOICE_ID")
        if not api_key or not voice_id:
            return None
        try:
            import httpx
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": api_key,
                "accept": "audio/mpeg",
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "model_id": os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2"),
                "voice_settings": {
                    "stability": float(os.getenv("ELEVENLABS_STABILITY", "0.5")),
                    "similarity_boost": float(os.getenv("ELEVENLABS_SIMILARITY", "0.85")),
                    "style": float(os.getenv("ELEVENLABS_STYLE", "0.3")),
                    "use_speaker_boost": True,
                },
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.content
            tmp = Path(tempfile.mkstemp(suffix=".mp3")[1])
            with open(tmp, "wb") as f:
                f.write(data)
            return tmp
        except Exception as e:
            print(f"[VoiceEngine] ElevenLabs TTS error: {e}")
            return None

    async def _tts_piper(self, text: str) -> Optional[Path]:
        model = self.config.piper_model_path or os.getenv("PIPER_MODEL_PATH")
        if not model:
            return None
        try:
            out_path = Path(tempfile.mkstemp(suffix=".wav")[1])
            # Pipe text to piper stdin
            import subprocess
            proc = await asyncio.create_subprocess_exec(
                self.config.piper_bin,
                "-m", model,
                "-f", str(out_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert proc.stdin is not None
            proc.stdin.write(text.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()
            await proc.wait()
            if proc.returncode == 0 and out_path.exists():
                return out_path
            else:
                stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
                print(f"[VoiceEngine] Piper error: {stderr}")
                return None
        except Exception as e:
            print(f"[VoiceEngine] Piper invocation error: {e}")
            return None

    async def _play_file(self, path: Path) -> None:
        try:
            import subprocess
            # macOS can play mp3/wav with afplay
            await asyncio.create_subprocess_exec("afplay", str(path))
        except Exception as e:
            print(f"[VoiceEngine] Playback error: {e}")
        finally:
            # Do not delete immediately; allow playback process to read. Caller may clean up later if desired.
            pass
    
    async def speak_response(self, text: str) -> None:
        if not self.config.enable_tts:
            return
        try:
            print(f"[VoiceEngine] Speaking: '{text}'")
            clean_text = self._clean_text_for_speech(text)

            # Choose provider
            provider = (self.config.tts_provider or "auto").lower()
            audio_path: Optional[Path] = None

            if provider in ("auto", "elevenlabs"):
                audio_path = await self._tts_elevenlabs(clean_text)
                if audio_path is None and provider == "elevenlabs":
                    print("[VoiceEngine] ElevenLabs requested but not available")
                if audio_path:
                    await self._play_file(audio_path)
                    return

            if provider in ("auto", "piper"):
                audio_path = await self._tts_piper(clean_text)
                if audio_path:
                    await self._play_file(audio_path)
                    return

            # Fallback to macOS say
            import subprocess
            base_wpm = max(120, min(240, self.config.voice_rate_wpm))
            rate = int(base_wpm * max(0.6, min(1.4, self.config.voice_speed)))
            args = [
                'say',
                '-v', self.config.voice_name,
                '-r', str(rate),
                clean_text
            ]
            subprocess.run(args, check=False)
        except Exception as e:
            print(f"[VoiceEngine] TTS error: {e}")

    def _clean_text_for_speech(self, text: str) -> str:
        import re
        text = re.sub(r'CALL_\w+\([^)]+\)', '', text)
        text = re.sub(r'[*_`#]', '', text)
        text = text.replace('✅', 'Success!').replace('⚙️', 'Working...').replace('❌', 'Error:')
        return text.strip()
    
    def __del__(self):
        pass  # Nothing to clean up in simplified mode