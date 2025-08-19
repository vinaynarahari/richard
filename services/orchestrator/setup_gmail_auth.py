#!/usr/bin/env python3
"""
One-time Gmail OAuth setup script.
This script will help you authenticate your Gmail accounts once, 
and then the system will automatically refresh tokens as needed.

Usage:
    python setup_gmail_auth.py
"""

import os
import sys
import json
import webbrowser
from urllib.parse import urlencode, parse_qs, urlparse
import httpx

def get_auth_url():
    """Get the Google OAuth authorization URL"""
    try:
        response = httpx.get("http://127.0.0.1:8000/oauth/google/authorize_url", timeout=10)
        if response.status_code != 200:
            print(f"Error getting auth URL: {response.text}")
            print("\n💡 Make sure the orchestrator server is running on port 8000:")
            print("   cd /Users/vinaynarahari/Desktop/Github/richard")
            print("   uvicorn app.main:app --app-dir services/orchestrator --reload --host 127.0.0.1 --port 8000")
            sys.exit(1)
        return response.json()["authorize_url"]
    except httpx.ConnectError:
        print("❌ Cannot connect to orchestrator server on port 8000")
        print("\n💡 Make sure the orchestrator server is running:")
        print("   cd /Users/vinaynarahari/Desktop/Github/richard")
        print("   uvicorn app.main:app --app-dir services/orchestrator --reload --host 127.0.0.1 --port 8000")
        sys.exit(1)

def exchange_code(account: str, code: str):
    """Exchange authorization code for tokens"""
    response = httpx.post(
        "http://127.0.0.1:8000/oauth/google/exchange",
        json={"account": account, "code": code}
    )
    if response.status_code != 200:
        print(f"Error exchanging code: {response.text}")
        return False
    print(f"✅ Successfully authenticated {account}")
    return True

def main():
    print("🔐 Gmail OAuth Setup")
    print("===================")
    print()
    
    # Get the accounts to set up
    accounts = []
    while True:
        email = input("Enter Gmail account to authenticate (or press Enter to finish): ").strip()
        if not email:
            break
        if "@" not in email:
            print("Please enter a valid email address")
            continue
        accounts.append(email)
    
    if not accounts:
        print("No accounts provided. Exiting.")
        sys.exit(0)
    
    print(f"\n📧 Setting up OAuth for {len(accounts)} account(s):")
    for i, account in enumerate(accounts, 1):
        print(f"  {i}. {account}")
    
    print("\n🌐 Getting OAuth authorization URL...")
    auth_url = get_auth_url()
    
    print(f"\n🔗 Opening browser to: {auth_url}")
    webbrowser.open(auth_url)
    
    print("\n📋 Instructions:")
    print("1. The browser should open to Google's OAuth consent page")
    print("2. Sign in and grant permissions for each account")
    print("3. After granting permissions, you'll be redirected to a URL like:")
    print("   http://127.0.0.1:5273/callback/google?code=4/XXXXXX...")
    print("4. Copy the 'code' parameter value from that URL")
    print()
    
    # Authenticate each account
    success_count = 0
    for i, account in enumerate(accounts, 1):
        print(f"\n🔑 Authenticating account {i}/{len(accounts)}: {account}")
        print("Please complete the OAuth flow for this account in your browser.")
        
        while True:
            code = input(f"Enter the authorization code for {account}: ").strip()
            if not code:
                print("Please enter the authorization code")
                continue
            
            if exchange_code(account, code):
                success_count += 1
                break
            else:
                retry = input("Would you like to try again? (y/n): ").strip().lower()
                if retry != 'y':
                    break
    
    print(f"\n✨ Setup complete!")
    print(f"   Successfully authenticated: {success_count}/{len(accounts)} accounts")
    
    if success_count > 0:
        print("\n🎉 Your Gmail accounts are now set up!")
        print("   The system will automatically refresh tokens as needed.")
        print("   You shouldn't need to do this setup again unless you revoke access.")
    
    if success_count < len(accounts):
        print(f"\n⚠️  {len(accounts) - success_count} account(s) failed to authenticate.")
        print("   You can run this script again to retry failed accounts.")

if __name__ == "__main__":
    main()