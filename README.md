# Richard

Local-first, macOS assistant with a Swift/SwiftUI menubar UI and a Python orchestrator. Default model: gpt-oss with dynamic routing to DeepSeek R1, Qwen 3, and Phi-3 where advantageous. Secure OAuth flows, Keychain token storage, and SQLCipher-encrypted memory/config.

source services/orchestrator/.venv/bin/activate; uvicorn app.main:app --app-dir services/orchestrator --reload --host 127.0.0.1 --port 5273

This repo currently contains the initial scaffold plan. Next steps will add code for:
- apps/menubar (Swift/SwiftUI)
- services/orchestrator (Python/FastAPI)
- packages/shared (schemas)
- config (env templates)

### Quick start (venv + uvicorn)

- **Create and activate a virtualenv**
  ```bash
cd /Users/vinaynarahari/Desktop/Github/richard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
  ```

- **Install server deps**
  ```bash
pip install fastapi uvicorn[standard]
  ```

- **Scaffold a minimal FastAPI app**
  ```bash
mkdir -p /Users/vinaynarahari/Desktop/Github/richard/services/orchestrator
cat > /Users/vinaynarahari/Desktop/Github/richard/services/orchestrator/main.py << 'PY'
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
PY
  ```

- **Run uvicorn**
  ```bash
cd /Users/vinaynarahari/Desktop/Github/richard
source .venv/bin/activate
uvicorn app.main:app --app-dir services/orchestrator --reload --host 127.0.0.1
  ```
cd /Users/vinaynarahari/Desktop/Github/richard/services/orchestrator && ./.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1
- **Test**
  ```bash
curl http://127.0.0.1:8000/health
  ```

- **Stop server**
  - Ctrl+C in the terminal.

- **(Optional) Save requirements**
  ```bash
pip freeze > requirements.txt
  ```

- **(Optional) Deactivate venv**
  ```bash
deactivate
  ```

- If you already have a FastAPI app file, adjust the uvicorn target accordingly (e.g., `uvicorn services.orchestrator.main:app --reload`). 

- If you want, I can run these for you automatically.
