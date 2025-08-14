#!/usr/bin/env python3
"""Setup script for MCP servers."""

import os
import subprocess
import sys
from pathlib import Path

def install_server_dependencies(server_path: Path):
    """Install dependencies for a specific MCP server."""
    requirements_file = server_path / "requirements.txt"
    if requirements_file.exists():
        print(f"Installing dependencies for {server_path.name}...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
        ])
    else:
        print(f"No requirements.txt found for {server_path.name}")

def main():
    """Main setup function."""
    mcp_servers_dir = Path(__file__).parent
    
    # Install dependencies for each server
    server_dirs = [d for d in mcp_servers_dir.iterdir() 
                   if d.is_dir() and d.name not in ['.git', '__pycache__']]
    
    for server_dir in server_dirs:
        install_server_dependencies(server_dir)
    
    print("\n✅ MCP servers setup complete!")
    print("\n📝 Next steps:")
    print("1. Copy .env.example to .env and fill in your API keys")
    print("2. Configure your MCP client to use the servers in config.json")
    print("3. Test the servers using the test scripts")

if __name__ == "__main__":
    main()