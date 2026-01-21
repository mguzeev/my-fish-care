#!/usr/bin/env python3
"""Simple structure test for vision API."""
import os
import sys

def test_structure():
    """Test the basic structure."""
    tests_passed = 0
    tests_total = 0
    
    print("\n" + "=" * 60)
    print("VISION API STRUCTURE TEST")
    print("=" * 60 + "\n")
    
    # Test 1: Database fields
    print("TEST 1: Database Migration")
    print("-" * 60)
    tests_total += 1
    try:
        import sqlite3
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(llm_models)")
        llm_columns = [row[1] for row in cursor.fetchall()]
        has_text = 'supports_text' in llm_columns
        has_vision = 'supports_vision' in llm_columns
        
        cursor.execute("PRAGMA table_info(usage_records)")
        usage_columns = [row[1] for row in cursor.fetchall()]
        has_image = 'has_image' in usage_columns
        
        conn.close()
        
        if has_text and has_vision and has_image:
            print("✅ PASS: All new database fields present")
            print(f"   - llm_models.supports_text: {has_text}")
            print(f"   - llm_models.supports_vision: {has_vision}")
            print(f"   - usage_records.has_image: {has_image}")
            tests_passed += 1
        else:
            print("❌ FAIL: Missing database fields")
    except Exception as e:
        print(f"❌ FAIL: {e}")
    
    # Test 2: Media directory
    print("\nTEST 2: Media Directory Structure")
    print("-" * 60)
    tests_total += 1
    media_dir = "media/uploads"
    if os.path.exists(media_dir) and os.path.isdir(media_dir):
        print(f"✅ PASS: Media directory exists at {media_dir}")
        tests_passed += 1
    else:
        print(f"❌ FAIL: Media directory missing at {media_dir}")
    
    # Test 3: API schemas
    print("\nTEST 3: API Schema Updates")
    print("-" * 60)
    tests_total += 1
    try:
        from app.agents.schemas import AgentInvokeRequest, AgentResponse
        
        # Check if new fields exist
        req = AgentInvokeRequest(input="test")
        has_image_path = hasattr(req, 'image_path')
        
        resp_fields = AgentResponse.__fields__
        has_agent_name = 'agent_name' in resp_fields
        has_processed_image = 'processed_image' in resp_fields
        
        if has_image_path and has_agent_name and has_processed_image:
            print("✅ PASS: All new schema fields present")
            print(f"   - AgentInvokeRequest.image_path: {has_image_path}")
            print(f"   - AgentResponse.agent_name: {has_agent_name}")
            print(f"   - AgentResponse.processed_image: {has_processed_image}")
            tests_passed += 1
        else:
            print("❌ FAIL: Missing schema fields")
    except Exception as e:
        print(f"❌ FAIL: {e}")
    
    # Test 4: AgentRuntime methods
    print("\nTEST 4: AgentRuntime Image Support")
    print("-" * 60)
    tests_total += 1
    try:
        from app.agents.runtime import AgentRuntime
        runtime = AgentRuntime()
        
        has_load_image = hasattr(runtime, '_load_image_as_base64')
        has_build_with_image = hasattr(runtime, '_build_messages_with_image')
        
        if has_load_image and has_build_with_image:
            print("✅ PASS: AgentRuntime has image support methods")
            print(f"   - _load_image_as_base64: {has_load_image}")
            print(f"   - _build_messages_with_image: {has_build_with_image}")
            tests_passed += 1
        else:
            print("❌ FAIL: Missing image support methods")
    except Exception as e:
        print(f"❌ FAIL: {e}")
    
    # Test 5: Agent selection function
    print("\nTEST 5: Auto Agent Selection")
    print("-" * 60)
    tests_total += 1
    try:
        from app.agents.router import _get_first_available_agent
        print("✅ PASS: _get_first_available_agent function exists")
        tests_passed += 1
    except Exception as e:
        print(f"❌ FAIL: {e}")
    
    # Test 6: Upload endpoint
    print("\nTEST 6: Upload Endpoint")
    print("-" * 60)
    tests_total += 1
    try:
        from app.channels.web import router
        # Check if upload endpoint exists in routes
        upload_found = False
        for route in router.routes:
            if hasattr(route, 'path') and 'upload-image' in route.path:
                upload_found = True
                break
        
        if upload_found:
            print("✅ PASS: /web/upload-image endpoint registered")
            tests_passed += 1
        else:
            print("❌ FAIL: Upload endpoint not found")
    except Exception as e:
        print(f"❌ FAIL: {e}")
    
    # Test 7: Test image file
    print("\nTEST 7: Test Image File")
    print("-" * 60)
    tests_total += 1
    if os.path.exists('/tmp/test_image.jpg'):
        size = os.path.getsize('/tmp/test_image.jpg')
        print(f"✅ PASS: Test image exists ({size} bytes)")
        tests_passed += 1
    else:
        print("❌ FAIL: Test image not found at /tmp/test_image.jpg")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"SUMMARY: {tests_passed}/{tests_total} tests passed")
    print("=" * 60 + "\n")
    
    return tests_passed == tests_total


if __name__ == "__main__":
    success = test_structure()
    sys.exit(0 if success else 1)
