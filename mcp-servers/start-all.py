#!/usr/bin/env python3
"""
Unified startup script for all MCP servers.
Supports both Python and Node.js servers with proper environment setup.
"""

import os
import sys
import json
import subprocess
import signal
import threading
import time
from pathlib import Path
from typing import Dict, List, Any

# Load orchestrator environment variables
from load_orchestrator_env import load_orchestrator_env
load_orchestrator_env()

class MCPServerManager:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.config_file = Path(__file__).parent / "config.json"
        self.running = False
        
    def load_config(self) -> Dict[str, Any]:
        """Load server configuration from config.json."""
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print("❌ config.json not found. Creating default configuration...")
            return self.create_default_config()
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing config.json: {e}")
            sys.exit(1)
    
    def create_default_config(self) -> Dict[str, Any]:
        """Create default configuration for all detected servers."""
        config = {"mcpServers": {}}
        
        # Detect Python servers
        python_servers = ["gmail", "notion", "google-search", "security"]
        for server in python_servers:
            server_path = Path(__file__).parent / server / "server.py"
            if server_path.exists():
                config["mcpServers"][server] = {
                    "command": "python",
                    "args": [f"{server}/server.py"],
                    "env": {
                        "PYTHONPATH": "."
                    }
                }
        
        # Detect Node.js servers
        playwright_path = Path(__file__).parent / "playwright-search"
        if (playwright_path / "package.json").exists():
            config["mcpServers"]["playwright-search"] = {
                "command": "node",
                "args": ["cli.js"],
                "cwd": "playwright-search",
                "env": {}
            }
        
        # Save default config
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Created default config.json with {len(config['mcpServers'])} servers")
        return config
    
    def start_server(self, name: str, config: Dict[str, Any]) -> bool:
        """Start a single MCP server."""
        try:
            command = config.get("command", "python")
            args = config.get("args", [])
            env_vars = config.get("env", {})
            cwd = config.get("cwd")
            
            # Prepare environment
            env = os.environ.copy()
            for key, value in env_vars.items():
                # Handle environment variable substitution
                if value.startswith("${") and value.endswith("}"):
                    env_key = value[2:-1]
                    env[key] = os.getenv(env_key, "")
                else:
                    env[key] = value
            
            # Prepare working directory
            if cwd:
                work_dir = Path(__file__).parent / cwd
            else:
                work_dir = Path(__file__).parent
            
            # Start the process
            full_command = [command] + args
            print(f"🚀 Starting {name}: {' '.join(full_command)}")
            
            process = subprocess.Popen(
                full_command,
                cwd=work_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.processes[name] = process
            
            # Start output monitoring thread
            threading.Thread(
                target=self.monitor_output,
                args=(name, process),
                daemon=True
            ).start()
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to start {name}: {e}")
            return False
    
    def monitor_output(self, name: str, process: subprocess.Popen):
        """Monitor server output and print with prefix."""
        while process.poll() is None and self.running:
            try:
                # Read stdout
                if process.stdout:
                    line = process.stdout.readline()
                    if line:
                        print(f"[{name}] {line.strip()}")
                
                # Check for errors
                if process.stderr:
                    error_line = process.stderr.readline()
                    if error_line:
                        print(f"[{name}] ERROR: {error_line.strip()}")
                        
            except Exception:
                break
    
    def stop_all_servers(self):
        """Stop all running servers."""
        print("\n🛑 Stopping all servers...")
        self.running = False
        
        for name, process in self.processes.items():
            if process.poll() is None:
                print(f"  ✋ Stopping {name}...")
                process.terminate()
                
                # Wait for graceful shutdown
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"  🔨 Force killing {name}...")
                    process.kill()
        
        self.processes.clear()
        print("✅ All servers stopped")
    
    def start_all_servers(self, server_filter: List[str] = None):
        """Start all configured servers or a filtered subset."""
        config = self.load_config()
        servers = config.get("mcpServers", {})
        
        if not servers:
            print("❌ No servers configured in config.json")
            return
        
        # Filter servers if specified
        if server_filter:
            servers = {name: config for name, config in servers.items() 
                      if name in server_filter}
        
        print(f"🌟 Starting {len(servers)} MCP server(s)...")
        print("=" * 50)
        
        self.running = True
        started_count = 0
        
        for name, server_config in servers.items():
            if self.start_server(name, server_config):
                started_count += 1
                time.sleep(1)  # Brief delay between starts
        
        print("=" * 50)
        print(f"✅ Started {started_count}/{len(servers)} servers successfully")
        
        if started_count > 0:
            print("\n📋 Server Status:")
            for name in servers.keys():
                if name in self.processes:
                    status = "🟢 Running" if self.processes[name].poll() is None else "🔴 Stopped"
                    print(f"  {name}: {status}")
            
            print("\n💡 Press Ctrl+C to stop all servers")
            
            # Wait for keyboard interrupt
            try:
                while self.running:
                    time.sleep(1)
                    # Check if any process died
                    for name, process in list(self.processes.items()):
                        if process.poll() is not None:
                            print(f"⚠️  {name} server stopped unexpectedly")
                            del self.processes[name]
            except KeyboardInterrupt:
                pass
            finally:
                self.stop_all_servers()

def main():
    """Main function."""
    manager = MCPServerManager()
    
    # Handle signal interruption
    def signal_handler(signum, frame):
        manager.stop_all_servers()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] in ["--help", "-h"]:
            print("Usage: python start-all.py [server1] [server2] ...")
            print("       python start-all.py --list")
            print("")
            print("Start all MCP servers or specific ones.")
            print("")
            print("Options:")
            print("  --help, -h    Show this help message")
            print("  --list, -l    List available servers")
            print("")
            print("Examples:")
            print("  python start-all.py                    # Start all servers")
            print("  python start-all.py gmail notion       # Start only gmail and notion")
            return
        
        elif sys.argv[1] in ["--list", "-l"]:
            config = manager.load_config()
            servers = config.get("mcpServers", {})
            print("Available MCP servers:")
            for name, config in servers.items():
                command = config.get("command", "unknown")
                print(f"  📦 {name} ({command})")
            return
        
        else:
            # Start specific servers
            server_list = sys.argv[1:]
            manager.start_all_servers(server_list)
            return
    
    # Start all servers
    manager.start_all_servers()

if __name__ == "__main__":
    main()