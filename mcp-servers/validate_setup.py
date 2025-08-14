#!/usr/bin/env python3
"""Validate the complete MCP servers setup."""

import os
import sys
import subprocess
import asyncio
from pathlib import Path

# Load orchestrator environment variables
from load_orchestrator_env import load_orchestrator_env
load_orchestrator_env()

def check_files():
    """Check that all required files exist."""
    print("📁 Checking file structure...")
    
    required_files = [
        "gmail/server.py",
        "gmail/gmail_client.py", 
        "gmail/requirements.txt",
        "notion/server.py",
        "notion/notion_api_client.py",
        "notion/requirements.txt", 
        "google-search/server.py",
        "google-search/google_search_client.py",
        "google-search/requirements.txt",
        "config.json",
        "README.md"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print(f"  ❌ Missing files: {missing_files}")
        return False
    else:
        print(f"  ✅ All {len(required_files)} required files present")
        return True

def check_dependencies():
    """Check that required Python packages are installed."""
    print("\n📦 Checking dependencies...")
    
    # Test actual imports that servers use
    package_tests = [
        ("mcp", "mcp.server"),
        ("google-api-python-client", "googleapiclient.discovery"),
        ("notion-client", "notion_client"),
        ("httpx", "httpx")
    ]
    
    missing_packages = []
    for package_name, import_name in package_tests:
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(package_name)
    
    if missing_packages:
        print(f"  ❌ Missing packages: {missing_packages}")
        print("    Run: pip install " + " ".join(missing_packages))
        return False
    else:
        print(f"  ✅ All {len(package_tests)} required packages installed")
        return True

def check_environment():
    """Check environment variables."""
    print("\n🔧 Checking environment...")
    
    env_vars = [
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET", 
        "NOTION_CLIENT_SECRET"
    ]
    
    present_vars = 0
    for var in env_vars:
        if os.getenv(var):
            print(f"  ✅ {var}")
            present_vars += 1
        else:
            print(f"  ⚠️  {var} not set")
    
    print(f"  📊 {present_vars}/{len(env_vars)} environment variables configured")
    return present_vars > 0

def test_health_checks():
    """Test server health checks."""
    print("\n🏥 Testing server health checks...")
    
    servers = ["gmail", "notion", "google-search"]
    healthy_servers = 0
    
    for server in servers:
        try:
            result = subprocess.run(
                [sys.executable, f"{server}/server.py", "--health"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                print(f"  ✅ {server} server healthy")
                healthy_servers += 1
            else:
                print(f"  ❌ {server} server unhealthy")
                if result.stderr:
                    print(f"    Error: {result.stderr.strip()}")
                    
        except subprocess.TimeoutExpired:
            print(f"  ⏰ {server} server health check timed out")
        except Exception as e:
            print(f"  ❌ {server} server error: {e}")
    
    print(f"  📊 {healthy_servers}/{len(servers)} servers healthy")
    return healthy_servers == len(servers)

def main():
    """Run complete validation."""
    print("🔍 MCP Servers Setup Validation")
    print("=" * 40)
    
    checks = [
        ("File Structure", check_files),
        ("Dependencies", check_dependencies), 
        ("Environment", check_environment),
        ("Health Checks", test_health_checks)
    ]
    
    passed_checks = 0
    
    for check_name, check_func in checks:
        try:
            if check_func():
                passed_checks += 1
        except Exception as e:
            print(f"\n❌ {check_name} check failed: {e}")
    
    print(f"\n📊 Validation Summary: {passed_checks}/{len(checks)} checks passed")
    
    if passed_checks == len(checks):
        print("\n🎉 All checks passed! MCP servers are ready to use.")
        print("\n🚀 Quick start:")
        print("  • Start a server: python run_server.py gmail")
        print("  • Use config.json to configure your MCP client")
        print("  • See README.md for detailed usage instructions")
    else:
        print(f"\n⚠️  {len(checks) - passed_checks} checks failed. See output above for details.")
        
    print("\n📚 Documentation: See README.md for complete setup instructions")

if __name__ == "__main__":
    main()