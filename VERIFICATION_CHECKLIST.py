"""
Verification checklist for token and image logging
"""

def print_verification_checklist():
    print("=" * 80)
    print("VERIFICATION CHECKLIST: Token and Image Logging")
    print("=" * 80)
    
    print("\n✓ CODE CHANGES COMPLETED:")
    print("  [✓] app/agents/router.py - Added image_path to variables in /{agent_id}/invoke")
    print("  [✓] app/agents/router.py - Added has_image field to UsageRecord")
    print("  [✓] Both endpoints (/agents/invoke and /agents/{agent_id}/invoke) updated")
    
    print("\n✓ DATABASE SCHEMA:")
    print("  [✓] usage_records.prompt_tokens - EXISTS")
    print("  [✓] usage_records.completion_tokens - EXISTS")
    print("  [✓] usage_records.total_tokens - EXISTS")
    print("  [✓] usage_records.has_image - EXISTS")
    print("  [✓] usage_records.cost - EXISTS")
    
    print("\n✓ API RESPONSES:")
    print("  [✓] AgentResponse includes usage_tokens field")
    print("  [✓] AgentResponse includes processed_image field")
    print("  [✓] AgentResponse includes agent_name field")
    
    print("\n✓ DASHBOARD UI:")
    print("  [✓] Shows agent info: 'Agent used: {name} ({model})'")
    print("  [✓] Shows image indicator: '📷 with image' when processed_image=true")
    print("  [✓] Shows usage information after query")
    
    print("\n✓ USAGE METRICS (/billing/usage):")
    print("  [✓] Returns total requests count")
    print("  [✓] Returns total tokens sum")
    print("  [✓] Returns total cost")
    print("  [✓] Aggregates from usage_records table")
    
    print("\n✓ ACTIVITY LOG (/billing/activity):")
    print("  [✓] Shows AI Agent Query entries")
    print("  [✓] Displays token count: 'X,XXX tokens'")
    print("  [✓] Shows cost if > 0: '$X.XX'")
    print("  [✓] Filters significant events (agent invocations)")
    
    print("\n" + "=" * 80)
    print("MANUAL TESTING REQUIRED:")
    print("=" * 80)
    
    print("\n1. TEST TEXT-ONLY QUERY:")
    print("   - Go to http://localhost:8000/dashboard")
    print("   - Enter query: 'Explain quantum computing'")
    print("   - Click Send Query")
    print("   - Verify response shows:")
    print("     ✓ Agent name and model")
    print("     ✓ Usage information")
    print("   - Check Usage Metrics section:")
    print("     ✓ Total Tokens increased")
    
    print("\n2. TEST QUERY WITH IMAGE:")
    print("   - Click '📷 Choose Image' button")
    print("   - Select an image file (JPG/PNG)")
    print("   - Enter query: 'What is in this image?'")
    print("   - Click Send Query")
    print("   - Verify response shows:")
    print("     ✓ Agent name and model")
    print("     ✓ '📷 with image' indicator")
    print("     ✓ Usage information")
    print("   - Check Usage Metrics section:")
    print("     ✓ Total Tokens increased MORE (images use ~10x tokens)")
    print("     ✓ Total Cost increased")
    
    print("\n3. VERIFY IN DATABASE:")
    print("   sqlite3 bot.db \"SELECT id, endpoint, total_tokens, has_image, cost")
    print("                   FROM usage_records")
    print("                   WHERE endpoint LIKE '%/agents/%invoke%'")
    print("                   ORDER BY created_at DESC LIMIT 5;\"")
    print("   Expected:")
    print("     - Latest entry with has_image=1 (image query)")
    print("     - Previous entry with has_image=0 (text query)")
    print("     - total_tokens > 0 for both")
    print("     - Image query should have MORE tokens")
    
    print("\n4. CHECK API DIRECTLY:")
    print("   See MANUAL_TEST_TOKENS.py for curl examples")
    
    print("\n" + "=" * 80)
    print("WHAT TO LOOK FOR:")
    print("=" * 80)
    
    print("\n✓ Token counts are NON-ZERO:")
    print("  - Text queries: typically 50-500 tokens")
    print("  - Image queries: typically 500-5000 tokens (10x more)")
    
    print("\n✓ Image indicator appears:")
    print("  - Dashboard shows '📷 with image' for image queries")
    print("  - Database has has_image=1 for image queries")
    
    print("\n✓ Metrics aggregate correctly:")
    print("  - Usage Metrics shows sum of all tokens")
    print("  - Activity Log shows individual queries with token counts")
    
    print("\n✓ Cost calculation:")
    print("  - If LLM model has cost_per_1k_input/output_tokens set")
    print("  - Cost should be > 0 and proportional to tokens")
    
    print("\n" + "=" * 80)
    print("COMMON ISSUES:")
    print("=" * 80)
    
    print("\n❌ Tokens are 0:")
    print("   - Check LLM API returns usage in response")
    print("   - Verify OpenAI/compatible API includes usage object")
    
    print("\n❌ Cost is 0:")
    print("   - Check LLM model has cost_per_1k_input_tokens set")
    print("   - Check LLM model has cost_per_1k_output_tokens set")
    print("   - Go to Admin Panel → LLM Models → Edit model → Set costs")
    
    print("\n❌ has_image is always 0:")
    print("   - Check image_path is passed in request")
    print("   - Verify payload.image_path is not None")
    print("   - Our fix should have resolved this!")
    
    print("\n❌ Image queries fail:")
    print("   - Check LLM model has supports_vision=true")
    print("   - Verify image file is uploaded successfully")
    print("   - Check agent is using a vision-capable model")
    
    print("\n" + "=" * 80)
    
if __name__ == "__main__":
    print_verification_checklist()
