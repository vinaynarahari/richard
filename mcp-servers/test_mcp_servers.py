#!/usr/bin/env python3
"""
Test script to verify MCP servers are working correctly.
"""

import json
import asyncio
import subprocess
import time
from pathlib import Path


async def test_mcp_server_stdio(server_command: list, server_name: str):
    """Test an MCP server using stdio transport."""
    print(f"\n🧪 Testing {server_name} MCP server...")
    
    try:
        # Start the server process
        process = subprocess.Popen(
            server_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(Path(__file__).parent)
        )
        
        # Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        # Send the request
        request_line = json.dumps(init_request) + "\n"
        process.stdin.write(request_line)
        process.stdin.flush()
        
        # Wait for response
        await asyncio.sleep(2)
        
        # Check if process is still running
        if process.poll() is None:
            print(f"✅ {server_name} server is responding")
            
            # Try to get available tools
            tools_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list"
            }
            
            tools_line = json.dumps(tools_request) + "\n"
            process.stdin.write(tools_line)
            process.stdin.flush()
            
            await asyncio.sleep(1)
            
            # Terminate the process
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            
            return True
        else:
            stderr_output = process.stderr.read() if process.stderr else ""
            print(f"❌ {server_name} server failed to start")
            if stderr_output:
                print(f"   Error: {stderr_output}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing {server_name}: {e}")
        if 'process' in locals():
            try:
                process.terminate()
            except:
                pass
        return False


async def test_playwright_server():
    """Test playwright-search server specifically."""
    print(f"\n🧪 Testing playwright-search MCP server...")
    
    try:
        # Test if the server starts and listens
        process = subprocess.Popen(
            ["node", "cli.js", "--headless", "--port", "3002"],
            cwd=str(Path(__file__).parent / "playwright-search"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Give it time to start
        await asyncio.sleep(3)
        
        if process.poll() is None:
            print("✅ playwright-search server started successfully")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            return True
        else:
            stdout, stderr = process.communicate()
            print("❌ playwright-search server failed to start")
            if stderr:
                print(f"   Error: {stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing playwright-search: {e}")
        if 'process' in locals():
            try:
                process.terminate()
            except:
                pass
        return False


async def main():
    """Run all MCP server tests."""
    print("🚀 Testing MCP Servers...")
    print("=" * 50)
    
    # Set PYTHONPATH for Python servers
    import os
    os.environ['PYTHONPATH'] = str(Path(__file__).parent)
    
    # Test each server
    servers_to_test = [
        (["python", "gmail/server.py"], "Gmail"),
        (["python", "notion/server.py"], "Notion"),
        (["python", "google-search/server.py"], "Google Search"),
    ]
    
    results = {}
    
    for server_cmd, server_name in servers_to_test:
        results[server_name] = await test_mcp_server_stdio(server_cmd, server_name)
    
    # Test playwright separately
    results["Playwright"] = await test_playwright_server()
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 Test Results:")
    
    all_passed = True
    for server_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {server_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 All MCP servers are working!")
        print("\n💡 Next steps:")
        print("   1. Start all servers: python start-all.py")
        print("   2. Configure your MCP client to connect to these servers")
        print("   3. Test specific tools via MCP client")
    else:
        print("\n⚠️  Some servers failed. Check the errors above.")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())