#!/usr/bin/env python3
"""Direct MiniMax API test - run from bench console or as standalone script"""
import os
import json
import requests

def test_minimax():
    api_key = os.getenv("MINIMAX_API_KEY")
    if not api_key:
        print("ERROR: MINIMAX_API_KEY not set")
        return
    
    base_url = "https://api.minimax.io/v1"
    
    # Test 1: OpenAI-compatible endpoint with MiniMax-M2
    print("\n=== Test 1: /chat/completions with MiniMax-M2 ===")
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "MiniMax-M2",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_completion_tokens": 100
            },
            timeout=30
        )
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 2: chatcompletion_v2 endpoint
    print("\n=== Test 2: /text/chatcompletion_v2 with MiniMax-M2 ===")
    try:
        resp = requests.post(
            f"{base_url}/text/chatcompletion_v2",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "MiniMax-M2",
                "messages": [
                    {"role": "system", "name": "assistant", "content": "You are a helpful assistant"},
                    {"role": "user", "name": "user", "content": "Hello"}
                ],
                "max_completion_tokens": 100
            },
            timeout=30
        )
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_minimax()
