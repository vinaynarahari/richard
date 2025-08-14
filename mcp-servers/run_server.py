#!/usr/bin/env python3
"""Run a specific MCP server with proper environment setup."""

import os
import sys
import asyncio
from pathlib import Path

# Load orchestrator environment variables
from load_orchestrator_env import load_orchestrator_env
load_orchestrator_env()

def main():
    """Main function to run a server."""
    if len(sys.argv) < 2:
        print("Usage: python run_server.py <server_name>")
        print("Available servers: gmail, notion, google-search")
        sys.exit(1)
    
    server_name = sys.argv[1]
    server_dir = Path(__file__).parent / server_name
    
    if not server_dir.exists() or not (server_dir / "server.py").exists():
        print(f"Error: Server '{server_name}' not found")
        sys.exit(1)
    
    print(f"🚀 Starting {server_name} MCP Server...")
    print("Press Ctrl+C to stop")
    print("-" * 40)
    
    # Change to server directory and run
    os.chdir(server_dir)
    
    # Add server directory to Python path
    sys.path.insert(0, str(server_dir))
    
    try:
        # Import and run the server
        import server
        # The server module should handle the main execution
        
    except KeyboardInterrupt:
        print("\n✋ Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()