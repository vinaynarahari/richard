import SwiftUI
import AVFoundation

struct RootPopoverView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        ZStack {
            TabView {
                // Replace Actions with Chat
                ChatView()
                    .tabItem { Label("Chat", systemImage: "message.fill") }

                ConnectionsView()
                    .tabItem { Label("Connections", systemImage: "link") }

                // Add Voice tab placeholder (will implement next)
                VoiceView()
                    .tabItem { Label("Voice", systemImage: "waveform") }

                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gearshape") }
            }
            .frame(minWidth: 400, minHeight: 480)
            .task { state.refreshOAuthStatus() }

            if let toast = state.toast {
                ToastView(toast: toast)
                    .onAppear {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2.4) { state.toast = nil }
                    }
            }
        }
    }
}

struct VoiceView: View {
    @EnvironmentObject var state: AppState
    @State private var isManualRecording = false
    @State private var recordingURL: URL?
    @State private var audioRecorder: AVAudioRecorder?
    @State private var transcriptText = ""
    @State private var showTranscript = false
    
    var body: some View {
        VStack(spacing: 20) {
            // Header
            HStack {
                Text("Voice Assistant")
                    .font(.title2)
                    .fontWeight(.semibold)
                Spacer()
                
                // Status indicator
                HStack(spacing: 4) {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 8, height: 8)
                    Text(statusText)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            // Wake word listening section
            VStack(spacing: 16) {
                Text("Always Listening")
                    .font(.headline)
                
                // Wake word detection visual
                ZStack {
                    Circle()
                        .fill(Color.blue.opacity(0.1))
                        .frame(width: 120, height: 120)
                    
                    if state.wakeWordDetected {
                        Circle()
                            .stroke(Color.blue, lineWidth: 3)
                            .frame(width: 130, height: 130)
                            .scaleEffect(state.wakeWordDetected ? 1.1 : 1.0)
                            .opacity(state.wakeWordDetected ? 0.8 : 0.2)
                            .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: state.wakeWordDetected)
                    }
                    
                    VStack {
                        Image(systemName: state.wakeWordDetected ? "waveform.circle.fill" : "waveform.circle")
                            .font(.system(size: 40))
                            .foregroundColor(state.wakeWordDetected ? .blue : .gray)
                        
                        Text(state.wakeWordDetected ? "Listening..." : "Say 'Hey Richard'")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                .onTapGesture {
                    // Simulate wake word for testing
                    state.simulateWakeWord()
                }
                
                HStack(spacing: 12) {
                    Button(state.isVoiceListening ? "Stop Listening" : "Start Listening") {
                        if state.isVoiceListening {
                            state.stopVoiceListening()
                        } else {
                            state.startVoiceListening()
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(state.isVoiceListening ? .red : .blue)
                }
            }
            
            Divider()
            
            // Manual recording section
            VStack(spacing: 16) {
                Text("Manual Recording")
                    .font(.headline)
                
                // Recording button with visual feedback
                ZStack {
                    Circle()
                        .fill(isManualRecording ? Color.red.opacity(0.2) : Color.gray.opacity(0.1))
                        .frame(width: 80, height: 80)
                    
                    if isManualRecording {
                        Circle()
                            .stroke(Color.red, lineWidth: 2)
                            .frame(width: 90, height: 90)
                            .scaleEffect(isManualRecording ? 1.1 : 1.0)
                            .opacity(isManualRecording ? 0.8 : 0.2)
                            .animation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true), value: isManualRecording)
                    }
                    
                    Button(action: toggleManualRecording) {
                        Image(systemName: isManualRecording ? "stop.fill" : "mic.fill")
                            .font(.system(size: 24))
                            .foregroundColor(isManualRecording ? .red : .blue)
                    }
                    .buttonStyle(PlainButtonStyle())
                }
                
                Text(isManualRecording ? "Recording... Tap to stop" : "Tap to record")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                // Transcription display
                if showTranscript && !transcriptText.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Transcription:")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        Text(transcriptText)
                            .padding(8)
                            .background(Color.gray.opacity(0.1))
                            .cornerRadius(8)
                            .font(.body)
                        
                        HStack {
                            Button("Send to Richard") {
                                sendTranscriptToRichard()
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(transcriptText.isEmpty)
                            
                            Button("Clear") {
                                transcriptText = ""
                                showTranscript = false
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                }
            }
            
            Spacer()
            
            // Status info
            if state.isProcessingVoice {
                HStack {
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Processing voice command...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            if !state.voiceResponse.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Richard's Response:")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(state.voiceResponse)
                        .padding(8)
                        .background(Color.blue.opacity(0.1))
                        .cornerRadius(8)
                        .font(.body)
                }
            }
        }
        .padding()
        .onAppear {
            setupAudioSession()
        }
    }
    
    private var statusColor: Color {
        if state.wakeWordDetected { return .blue }
        if state.isVoiceListening { return .green }
        if state.isProcessingVoice { return .orange }
        return .gray
    }
    
    private var statusText: String {
        if state.wakeWordDetected { return "Wake word detected" }
        if state.isVoiceListening { return "Listening" }
        if state.isProcessingVoice { return "Processing" }
        return "Inactive"
    }
    
    private func setupAudioSession() {
        // Audio session setup is handled automatically by AVAudioRecorder on macOS
        // No explicit session configuration needed
    }
    
    private func toggleManualRecording() {
        if isManualRecording {
            stopRecording()
        } else {
            startRecording()
        }
    }
    
    private func startRecording() {
        let documentsPath = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let audioFilename = documentsPath.appendingPathComponent("recording-\(Date().timeIntervalSince1970).wav")
        
        let settings = [
            AVFormatIDKey: Int(kAudioFormatLinearPCM),
            AVSampleRateKey: 16000,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsFloatKey: false,
        ] as [String : Any]
        
        do {
            audioRecorder = try AVAudioRecorder(url: audioFilename, settings: settings)
            audioRecorder?.record()
            
            recordingURL = audioFilename
            isManualRecording = true
            state.isRecording = true
            
        } catch {
            state.showError("Could not start recording: \(error.localizedDescription)")
        }
    }
    
    private func stopRecording() {
        audioRecorder?.stop()
        audioRecorder = nil
        isManualRecording = false
        state.isRecording = false
        
        // Transcribe the recording
        if let url = recordingURL {
            transcribeRecording(url: url)
        }
    }
    
    private func transcribeRecording(url: URL) {
        state.isProcessingVoice = true
        
        Task {
            do {
                let api = APIClient()
                let transcript = try await api.transcribe(audioWavURL: url)
                
                await MainActor.run {
                    transcriptText = transcript
                    showTranscript = true
                    state.isProcessingVoice = false
                    
                    // Clean up the audio file
                    try? FileManager.default.removeItem(at: url)
                    
                    if transcript.contains("transcription not available") {
                        state.showError("Transcription service unavailable - using text input")
                    } else if !transcript.isEmpty {
                        state.showSuccess("Recording transcribed successfully")
                    } else {
                        state.showError("No speech detected in recording")
                    }
                }
            } catch {
                await MainActor.run {
                    state.isProcessingVoice = false
                    state.showError("Transcription failed: \(error.localizedDescription)")
                }
            }
        }
    }
    
    private func sendTranscriptToRichard() {
        guard !transcriptText.isEmpty else { return }
        
        state.isProcessingVoice = true
        
        Task {
            do {
                let api = APIClient()
                try await api.sendVoiceCommand(transcriptText)
                
                await MainActor.run {
                    state.isProcessingVoice = false
                    state.voiceResponse = "Command sent to Richard successfully"
                    state.showSuccess("Voice command processed")
                    
                    // Clear the transcript after sending
                    transcriptText = ""
                    showTranscript = false
                }
            } catch {
                await MainActor.run {
                    state.isProcessingVoice = false
                    state.showError("Failed to send voice command: \(error.localizedDescription)")
                }
            }
        }
    }
}
