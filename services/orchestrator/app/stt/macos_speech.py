"""
macOS Speech Framework integration using PyObjC
"""

import logging
import tempfile
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    # Try to import PyObjC frameworks
    import objc
    from Foundation import NSBundle, NSURL
    from Speech import (
        SFSpeechRecognizer, 
        SFSpeechAudioBufferRecognitionRequest,
        SFSpeechRecognitionTask
    )
    from AVFoundation import (
        AVAudioEngine, 
        AVAudioFile,
        AVAudioFormat,
        AVAudioPCMBuffer
    )
    
    SPEECH_FRAMEWORK_AVAILABLE = True
    logger.info("macOS Speech Framework available")
    
except ImportError as e:
    SPEECH_FRAMEWORK_AVAILABLE = False
    logger.warning(f"macOS Speech Framework not available: {e}")


class MacOSSpeechRecognizer:
    """Native macOS Speech Framework recognizer"""
    
    def __init__(self, locale: str = "en-US"):
        self.locale = locale
        self.recognizer = None
        self.recognition_task = None
        self.audio_engine = None
        
        if SPEECH_FRAMEWORK_AVAILABLE:
            self._setup_recognizer()
    
    def _setup_recognizer(self):
        """Setup the speech recognizer"""
        try:
            # Create speech recognizer for locale
            from Foundation import NSLocale
            locale_obj = NSLocale.alloc().initWithLocaleIdentifier_(self.locale)
            self.recognizer = SFSpeechRecognizer.alloc().initWithLocale_(locale_obj)
            
            if not self.recognizer.isAvailable():
                logger.error("Speech recognizer not available")
                return False
                
            # Setup audio engine
            self.audio_engine = AVAudioEngine.alloc().init()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup speech recognizer: {e}")
            return False
    
    async def transcribe_audio_file(self, audio_file_path: str) -> Optional[str]:
        """Transcribe audio file using Speech Framework"""
        if not SPEECH_FRAMEWORK_AVAILABLE or not self.recognizer:
            return None
        
        try:
            # Load audio file
            audio_url = NSURL.fileURLWithPath_(audio_file_path)
            audio_file = AVAudioFile.alloc().initForReading_error_(audio_url, None)
            
            if not audio_file[0]:
                logger.error("Could not load audio file")
                return None
            
            audio_file = audio_file[0]
            
            # Get audio format
            audio_format = audio_file.processingFormat()
            
            # Read audio into buffer
            frame_count = int(audio_file.length())
            audio_buffer = AVAudioPCMBuffer.alloc().initWithPCMFormat_frameCapacity_(
                audio_format, frame_count
            )
            
            success = audio_file.readIntoBuffer_error_(audio_buffer, None)
            if not success[0]:
                logger.error("Could not read audio buffer")
                return None
            
            # Create recognition request
            request = SFSpeechAudioBufferRecognitionRequest.alloc().init()
            request.setShouldReportPartialResults_(False)
            
            # Append audio buffer
            request.appendAudioPCMBuffer_(audio_buffer)
            request.endAudio()
            
            # Perform recognition
            result_text = None
            recognition_complete = False
            
            def recognition_handler(result, error):
                nonlocal result_text, recognition_complete
                
                if error:
                    logger.error(f"Recognition error: {error}")
                    recognition_complete = True
                    return
                
                if result:
                    if result.isFinal():
                        result_text = str(result.bestTranscription().formattedString())
                        recognition_complete = True
                    
            # Start recognition
            self.recognition_task = self.recognizer.recognitionTask_resultHandler_(
                request, recognition_handler
            )
            
            # Wait for completion (with timeout)
            import time
            timeout = 30  # 30 seconds timeout
            elapsed = 0
            while not recognition_complete and elapsed < timeout:
                time.sleep(0.1)
                elapsed += 0.1
            
            if self.recognition_task:
                self.recognition_task.cancel()
                self.recognition_task = None
            
            return result_text
            
        except Exception as e:
            logger.error(f"macOS speech recognition failed: {e}")
            return None


# Create a simpler command-line based approach for macOS
class MacOSCommandLineSpeech:
    """Use macOS command-line tools for speech recognition"""
    
    @staticmethod
    async def transcribe_with_say_reverse(audio_file_path: str) -> Optional[str]:
        """
        Try to use macOS built-in tools for speech recognition
        This is a workaround approach
        """
        try:
            import subprocess
            import asyncio
            
            # Try using the 'speech' command if available
            try:
                result = await asyncio.create_subprocess_exec(
                    'which', 'speech',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await result.communicate()
                
                if result.returncode == 0:
                    # Use speech command
                    speech_result = await asyncio.create_subprocess_exec(
                        'speech', '--file', audio_file_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    stdout, stderr = await speech_result.communicate()
                    
                    if speech_result.returncode == 0:
                        text = stdout.decode().strip()
                        if text:
                            return text
                            
            except Exception:
                pass
            
            # Try AppleScript approach for dictation
            applescript = f'''
            tell application "System Events"
                try
                    -- This would require enabling dictation and accessibility access
                    -- For now, return nothing to fall back to other methods
                    return ""
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
            
            stdout, _ = await result.communicate()
            
            if result.returncode == 0:
                text = stdout.decode().strip()
                if text and len(text) > 1:
                    return text
                    
        except Exception as e:
            logger.error(f"macOS command-line speech failed: {e}")
        
        return None


def create_macos_recognizer(locale: str = "en-US") -> Optional[MacOSSpeechRecognizer]:
    """Create macOS speech recognizer if available"""
    if SPEECH_FRAMEWORK_AVAILABLE:
        return MacOSSpeechRecognizer(locale)
    return None