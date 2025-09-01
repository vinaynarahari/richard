#!/bin/bash

echo "🎤 Installing Fast Speech-to-Text services..."

# Install faster-whisper for local transcription
echo "📦 Installing faster-whisper..."
pip install faster-whisper

# Install required audio processing tools
echo "🔧 Installing audio processing dependencies..."
pip install httpx

# Check if FFmpeg is available
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpeg not found. Installing via Homebrew..."
    if command -v brew &> /dev/null; then
        brew install ffmpeg
    else
        echo "❌ Homebrew not found. Please install FFmpeg manually:"
        echo "   https://ffmpeg.org/download.html"
        exit 1
    fi
fi

echo "✅ Fast STT setup complete!"
echo ""
echo "🔑 Optional: Set API keys for fastest transcription:"
echo "   export OPENAI_API_KEY='your-openai-key'"
echo "   export GROQ_API_KEY='your-groq-key'"
echo ""
echo "⚡ Groq is recommended for fastest transcription (free tier available)"
echo "   Sign up at: https://console.groq.com"