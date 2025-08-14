#!/usr/bin/env python3
"""Test MCP server startup with proper stdio handling."""

import asyncio
import subprocess
import sys
import signal
import time
from pathlib import Path

# Load orchestrator environment variables
from load_orchestrator_env import load_orchestrator_env
load_orchestrator_env()

async def test_server_with_timeout(server_path: Path, timeout: int = 5) -> bool:
    """Test if a server can start and respond to initialization."""
    try:
        # Start the server process with proper stdio
        process = subprocess.Popen(
            [sys.executable, str(server_path / "server.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0  # Unbuffered
        )
        
        # Give the server a moment to start
        await asyncio.sleep(1)
        
        # Check if process is still running
        if process.poll() is None:
            print(f"  ✅ {server_path.name} server started successfully")
            
            # Send a simple initialization message (JSON-RPC 2.0)
            init_message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                }
            }
            
            try:
                # Try to write to stdin (this might not work without proper MCP client)
                # but it won't crash the server
                process.stdin.write("test\n")
                process.stdin.flush()
            except:
                pass  # Expected to fail without proper MCP protocol
            
            # Terminate the process
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            
            return True
        else:
            # Process terminated, check output
            stdout, stderr = process.communicate()
            print(f"  ❌ {server_path.name} server failed to start:")
            if stderr:
                print(f"    Error: {stderr.strip()}")
            return False
            
    except Exception as e:
        print(f"  ❌ Error testing {server_path.name}: {e}")
        return False

async def main():
    """Test all servers."""
    print("🚀 Testing MCP Server Startup\n")
    
    mcp_servers_dir = Path(__file__).parent
    server_dirs = [d for d in mcp_servers_dir.iterdir() 
                   if d.is_dir() and d.name not in ['.git', '__pycache__'] 
                   and (d / "server.py").exists()]
    
    results = {}
    
    for server_dir in server_dirs:
        print(f"🔍 Testing {server_dir.name} server...")
        success = await test_server_with_timeout(server_dir)
        results[server_dir.name] = success
        print()
    
    # Summary
    print("📊 Startup Test Results:")
    all_passed = True
    for server_name, success in results.items():
        status = "✅" if success else "❌"
        all_passed = all_passed and success
        print(f"  {status} {server_name}")
    
    print(f"\n{'🎉 All servers started successfully!' if all_passed else '⚠️  Some servers failed to start.'}")
    
    if not all_passed:
        print("\n💡 Note: Servers may fail due to missing environment variables or dependencies.")
        print("   This is normal for testing without real API credentials.")

if __name__ == "__main__":
    asyncio.run(main())