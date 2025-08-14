#!/usr/bin/env python3
"""Load environment variables from the orchestrator service."""

import os
import sys
from pathlib import Path

def load_orchestrator_env():
    """Load environment variables from the orchestrator .env file."""
    orchestrator_env_path = Path(__file__).parent / "../services/orchestrator/.env"
    
    if not orchestrator_env_path.exists():
        print(f"Warning: Orchestrator .env file not found at {orchestrator_env_path}")
        return
    
    with open(orchestrator_env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                os.environ[key] = value
    
    print("✅ Loaded orchestrator environment variables")

if __name__ == "__main__":
    load_orchestrator_env()