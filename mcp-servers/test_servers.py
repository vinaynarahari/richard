#!/usr/bin/env python3
"""Test script for MCP servers."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

# Load orchestrator environment variables
from load_orchestrator_env import load_orchestrator_env
load_orchestrator_env()


async def test_server_startup(server_path: Path) -> bool:
    """Test if a server can start up without errors."""
    try:
        # Start the server process
        process = subprocess.Popen(
            [sys.executable, str(server_path / "server.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait a bit for startup
        await asyncio.sleep(2)
        
        # Check if process is still running
        if process.poll() is None:
            # Process is still running, terminate it
            process.terminate()
            process.wait()
            return True
        else:
            # Process terminated, check output
            stdout, stderr = process.communicate()
            print(f"Server {server_path.name} failed to start:")
            print(f"STDOUT: {stdout}")
            print(f"STDERR: {stderr}")
            return False
            
    except Exception as e:
        print(f"Error testing server {server_path.name}: {e}")
        return False


async def test_server_imports(server_path: Path) -> bool:
    """Test if server dependencies can be imported."""
    try:
        # Check if we can import the main modules
        sys.path.insert(0, str(server_path))
        
        if server_path.name == "gmail":
            import gmail_client
            import server
        elif server_path.name == "notion":
            import notion_api_client
            import server
        elif server_path.name == "google-search":
            import google_search_client
            import server
        
        sys.path.remove(str(server_path))
        return True
        
    except ImportError as e:
        print(f"Import error in {server_path.name}: {e}")
        return False
    except Exception as e:
        print(f"Error testing imports for {server_path.name}: {e}")
        return False


def check_environment_variables() -> Dict[str, bool]:
    """Check if required environment variables are set."""
    required_vars = {
        "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID") is not None,
        "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET") is not None,
        "NOTION_CLIENT_SECRET": os.getenv("NOTION_CLIENT_SECRET") is not None
    }
    
    return required_vars


async def main():
    """Main test function."""
    print("🧪 Testing MCP Servers\n")
    
    mcp_servers_dir = Path(__file__).parent
    server_dirs = [d for d in mcp_servers_dir.iterdir() 
                   if d.is_dir() and d.name not in ['.git', '__pycache__']]
    
    # Check environment variables
    print("📋 Environment Variables:")
    env_vars = check_environment_variables()
    for var, is_set in env_vars.items():
        status = "✅" if is_set else "❌"
        print(f"  {status} {var}")
    print()
    
    # Test each server
    results = {}
    
    for server_dir in server_dirs:
        if not (server_dir / "server.py").exists():
            continue
            
        print(f"🔍 Testing {server_dir.name} server...")
        
        # Test imports
        import_success = await test_server_imports(server_dir)
        print(f"  Imports: {'✅' if import_success else '❌'}")
        
        # Test startup (only if imports work)
        startup_success = False
        if import_success:
            startup_success = await test_server_startup(server_dir)
            print(f"  Startup: {'✅' if startup_success else '❌'}")
        
        results[server_dir.name] = {
            "imports": import_success,
            "startup": startup_success
        }
        
        print()
    
    # Summary
    print("📊 Test Summary:")
    all_passed = True
    for server_name, tests in results.items():
        server_passed = all(tests.values())
        all_passed = all_passed and server_passed
        status = "✅" if server_passed else "❌"
        print(f"  {status} {server_name}")
    
    print(f"\n{'🎉 All tests passed!' if all_passed else '⚠️  Some tests failed. Check the output above.'}")
    
    if not all_passed:
        print("\n💡 Troubleshooting tips:")
        print("  1. Run 'python setup.py' to install dependencies")
        print("  2. Copy .env.example to .env and set your API keys")
        print("  3. Check that all required services are properly configured")


if __name__ == "__main__":
    asyncio.run(main())