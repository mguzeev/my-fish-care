#!/usr/bin/env python3
"""Test script for vision API endpoints."""
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"
TEST_IMAGE = "/tmp/test_image.jpg"

# Test credentials - using existing user
TEST_EMAIL = "devctrl508@gmail.com"
TEST_PASSWORD = "SuperSecret123!"  # Update this if needed


def print_result(test_name, success, details=""):
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status}: {test_name}")
    if details:
        print(f"   {details}")
    print()


def test_login():
    """Test user login."""
    print("=" * 60)
    print("TEST 1: User Login")
    print("=" * 60)
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token")
        print_result(
            "User Login",
            bool(token),
            f"Got access token: {token[:20]}..." if token else "No token"
        )
        return token
    else:
        print_result("User Login", False, f"Status: {response.status_code}, {response.text}")
        return None


def test_upload_image(token):
    """Test image upload endpoint."""
    print("=" * 60)
    print("TEST 2: Upload Image")
    print("=" * 60)
    
    if not token:
        print_result("Upload Image", False, "No auth token")
        return None
    
    try:
        with open(TEST_IMAGE, 'rb') as f:
            files = {'file': ('test.jpg', f, 'image/jpeg')}
            headers = {'Authorization': f'Bearer {token}'}
            
            response = requests.post(
                f"{BASE_URL}/web/upload-image",
                files=files,
                headers=headers
            )
        
        if response.status_code == 200:
            data = response.json()
            file_path = data.get("file_path")
            print_result(
                "Upload Image",
                data.get("success", False),
                f"File uploaded: {file_path}, Size: {data.get('file_size')} bytes"
            )
            return file_path
        else:
            print_result("Upload Image", False, f"Status: {response.status_code}, {response.text}")
            return None
    except Exception as e:
        print_result("Upload Image", False, f"Error: {str(e)}")
        return None


def test_invoke_agent_without_image(token):
    """Test agent invocation without image."""
    print("=" * 60)
    print("TEST 3: Invoke Agent (Text Only)")
    print("=" * 60)
    
    if not token:
        print_result("Invoke Agent (Text Only)", False, "No auth token")
        return
    
    payload = {
        "input": "Hello, what is 2+2?",
        "variables": {},
        "stream": False
    }
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    response = requests.post(
        f"{BASE_URL}/agents/invoke",
        json=payload,
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print_result(
            "Invoke Agent (Text Only)",
            True,
            f"Agent: {data.get('agent_name')}, Model: {data.get('model')}\n   Response: {data.get('output', '')[:100]}..."
        )
    else:
        print_result("Invoke Agent (Text Only)", False, f"Status: {response.status_code}, {response.text[:200]}")


def test_invoke_agent_with_image(token, image_path):
    """Test agent invocation with image."""
    print("=" * 60)
    print("TEST 4: Invoke Agent (With Image)")
    print("=" * 60)
    
    if not token:
        print_result("Invoke Agent (With Image)", False, "No auth token")
        return
    
    if not image_path:
        print_result("Invoke Agent (With Image)", False, "No image path")
        return
    
    payload = {
        "input": "What do you see in this image?",
        "image_path": image_path,
        "variables": {},
        "stream": False
    }
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    response = requests.post(
        f"{BASE_URL}/agents/invoke",
        json=payload,
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print_result(
            "Invoke Agent (With Image)",
            data.get('processed_image', False),
            f"Agent: {data.get('agent_name')}, Model: {data.get('model')}\n   Processed Image: {data.get('processed_image')}\n   Response: {data.get('output', '')[:100]}..."
        )
    elif response.status_code == 404:
        print_result(
            "Invoke Agent (With Image)",
            False,
            f"No vision agents available (expected if no GPT-4 Vision configured)"
        )
    else:
        print_result("Invoke Agent (With Image)", False, f"Status: {response.status_code}, {response.text[:200]}")


def test_database_migration():
    """Check if database has new fields."""
    print("=" * 60)
    print("TEST 5: Database Migration Check")
    print("=" * 60)
    
    try:
        import sqlite3
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        # Check llm_models table
        cursor.execute("PRAGMA table_info(llm_models)")
        llm_columns = [row[1] for row in cursor.fetchall()]
        has_supports_text = 'supports_text' in llm_columns
        has_supports_vision = 'supports_vision' in llm_columns
        
        # Check usage_records table
        cursor.execute("PRAGMA table_info(usage_records)")
        usage_columns = [row[1] for row in cursor.fetchall()]
        has_has_image = 'has_image' in usage_columns
        
        conn.close()
        
        all_fields = has_supports_text and has_supports_vision and has_has_image
        print_result(
            "Database Migration",
            all_fields,
            f"llm_models: supports_text={has_supports_text}, supports_vision={has_supports_vision}\n   usage_records: has_image={has_has_image}"
        )
    except Exception as e:
        print_result("Database Migration", False, f"Error: {str(e)}")


def test_media_directory():
    """Check if media directory exists."""
    print("=" * 60)
    print("TEST 6: Media Directory")
    print("=" * 60)
    
    import os
    media_dir = "/home/mguzieiev/maks/bot-generic/media/uploads"
    exists = os.path.exists(media_dir)
    is_dir = os.path.isdir(media_dir) if exists else False
    
    print_result(
        "Media Directory",
        exists and is_dir,
        f"Path: {media_dir}\n   Exists: {exists}, Is Directory: {is_dir}"
    )


def main():
    print("\n" + "=" * 60)
    print("VISION API TEST SUITE")
    print("=" * 60 + "\n")
    
    # Run tests
    test_database_migration()
    test_media_directory()
    
    token = test_login()
    
    if token:
        image_path = test_upload_image(token)
        test_invoke_agent_without_image(token)
        
        if image_path:
            test_invoke_agent_with_image(token, image_path)
    
    print("\n" + "=" * 60)
    print("TEST SUITE COMPLETED")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
