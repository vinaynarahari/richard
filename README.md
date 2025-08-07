# Richard

Local-first, macOS assistant with a Swift/SwiftUI menubar UI and a Python orchestrator. Default model: gpt-oss with dynamic routing to DeepSeek R1, Qwen 3, and Phi-3 where advantageous. Secure OAuth flows, Keychain token storage, and SQLCipher-encrypted memory/config.

This repo currently contains the initial scaffold plan. Next steps will add code for:
- apps/menubar (Swift/SwiftUI)
- services/orchestrator (Python/FastAPI)
- packages/shared (schemas)
- config (env templates)
