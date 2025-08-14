import AppKit
import SwiftUI

final class StatusBarController {
    private var statusItem: NSStatusItem
    private var popover: NSPopover
    private var isRecordingIndicatorActive = false

    init<T: View>(contentView: T) {
        popover = NSPopover()
        popover.contentSize = NSSize(width: 420, height: 520)
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(rootView: contentView)

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)

        // Prefer higher-priority behavior on newer macOS where available.
        // Note: There's no public `.app` behavior on the NSStatusItem.Behavior option set for our target SDKs.
        // Keep the item alive across removal/recreation; avoid unsupported flags to prevent build errors.
        if #available(macOS 14.0, *) {
            statusItem.behavior.insert(.terminationOnRemoval)
        }

        if let button = statusItem.button {
            // Use a symbol template so the system can render it compactly and keep it visible when space is tight.
            let image = NSImage(systemSymbolName: "brain.head.profile", accessibilityDescription: "Richard")
            image?.isTemplate = true
            button.image = image

            // Keep the footprint minimal: no text title; small but standard size so it can compress instead of disappearing.
            button.title = ""
            button.image?.size = NSSize(width: 16, height: 16)

            button.target = self
            button.action = #selector(togglePopover(_:))
        }
    }

    @objc func togglePopover(_ sender: AnyObject?) {
        if popover.isShown {
            popover.performClose(sender)
            return
        }
        if let button = statusItem.button {
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            popover.contentViewController?.view.window?.makeKey()
        }
    }
    
    // MARK: - Voice Recording Indicators
    func showRecordingIndicator() {
        guard let button = statusItem.button else { return }
        isRecordingIndicatorActive = true
        
        // Change icon to microphone when recording
        let image = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Richard Recording")
        image?.isTemplate = true
        button.image = image
        button.image?.size = NSSize(width: 16, height: 16)
        
        // Add pulsing animation
        startPulsingAnimation()
    }
    
    func hideRecordingIndicator() {
        guard let button = statusItem.button else { return }
        isRecordingIndicatorActive = false
        
        // Reset to default icon
        let image = NSImage(systemSymbolName: "brain.head.profile", accessibilityDescription: "Richard")
        image?.isTemplate = true
        button.image = image
        button.image?.size = NSSize(width: 16, height: 16)
        
        // Stop animation
        button.layer?.removeAllAnimations()
    }
    
    func showWakeWordIndicator() {
        guard let button = statusItem.button else { return }
        
        // Change icon to waveform when wake word detected
        let image = NSImage(systemSymbolName: "waveform.circle.fill", accessibilityDescription: "Richard Wake Word")
        image?.isTemplate = true
        button.image = image
        button.image?.size = NSSize(width: 16, height: 16)
        
        // Auto-hide after 2 seconds if not recording
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            if !self.isRecordingIndicatorActive {
                self.hideRecordingIndicator()
            }
        }
    }
    
    private func startPulsingAnimation() {
        guard let button = statusItem.button else { return }
        
        // Create pulsing opacity animation
        let animation = CABasicAnimation(keyPath: "opacity")
        animation.fromValue = 1.0
        animation.toValue = 0.3
        animation.duration = 1.0
        animation.autoreverses = true
        animation.repeatCount = .infinity
        
        button.layer?.add(animation, forKey: "pulseAnimation")
    }
}
