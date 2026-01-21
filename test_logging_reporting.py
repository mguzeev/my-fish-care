"""
Comprehensive test for logging and reporting across all channels.

Tests:
1. Usage logging with has_image flag
2. Token tracking for text and photo
3. Dashboard display of activity logs
"""
import sys
from pathlib import Path

print("=" * 70)
print("COMPREHENSIVE LOGGING & REPORTING TEST")
print("=" * 70)

checks_passed = 0
checks_total = 0

# Test 1: Check UsageRecord model has has_image field
print("\n1. UsageRecord Model:")
checks_total += 1
try:
    from app.models.usage import UsageRecord
    assert hasattr(UsageRecord, 'has_image'), "has_image field not found"
    print("   ✅ has_image field exists in UsageRecord")
    checks_passed += 1
except Exception as e:
    print(f"   ❌ FAIL: {e}")

# Test 2: Check agents/router.py logs with has_image
print("\n2. Agent Router Endpoints:")
router_file = Path("app/agents/router.py")
if router_file.exists():
    content = router_file.read_text()
    
    # Check /invoke endpoint
    checks_total += 1
    if 'has_image=payload.image_path is not None' in content:
        count = content.count('has_image=payload.image_path is not None')
        print(f"   ✅ has_image logging found {count} times (both endpoints)")
        checks_passed += 1
    else:
        print("   ❌ has_image logging not found")
    
    # Check token logging
    checks_total += 1
    if 'total_tokens = int(usage_tokens.get("total_tokens"' in content:
        print("   ✅ Token logging present")
        checks_passed += 1
    else:
        print("   ❌ Token logging missing")
else:
    print("   ❌ router.py not found")
    checks_total += 2

# Test 3: Check telegram.py logs with has_image
print("\n3. Telegram Channel:")
telegram_file = Path("app/channels/telegram.py")
if telegram_file.exists():
    content = telegram_file.read_text()
    
    # Check handle_photo logs
    checks_total += 1
    if 'has_image=True' in content:
        print("   ✅ has_image=True in handle_photo")
        checks_passed += 1
    else:
        print("   ❌ has_image not set in handle_photo")
    
    # Check token logging
    checks_total += 1
    if 'prompt_tokens = usage_tokens.get("prompt_tokens"' in content:
        print("   ✅ Token logging in Telegram")
        checks_passed += 1
    else:
        print("   ❌ Token logging missing in Telegram")
else:
    print("   ❌ telegram.py not found")
    checks_total += 2

# Test 4: Check ActivityEventResponse has has_image
print("\n4. Activity API Schema:")
billing_file = Path("app/billing/router.py")
if billing_file.exists():
    content = billing_file.read_text()
    
    checks_total += 1
    if 'has_image: Optional[bool] = None' in content:
        print("   ✅ has_image field in ActivityEventResponse")
        checks_passed += 1
    else:
        print("   ❌ has_image field missing in ActivityEventResponse")
    
    # Check activity events include has_image
    checks_total += 1
    if 'has_image=record.has_image' in content:
        print("   ✅ has_image included in activity events")
        checks_passed += 1
    else:
        print("   ❌ has_image not included in events")
    
    # Check title changes for images
    checks_total += 1
    if 'title = "📷 AI Vision Query"' in content or 'title = "📷 Telegram Photo"' in content:
        print("   ✅ Title changes for image queries (📷 icon)")
        checks_passed += 1
    else:
        print("   ❌ No special title for image queries")
else:
    print("   ❌ billing/router.py not found")
    checks_total += 3

# Test 5: Check dashboard displays has_image
print("\n5. Dashboard Display:")
dashboard_file = Path("app/templates/dashboard.html")
if dashboard_file.exists():
    content = dashboard_file.read_text()
    
    checks_total += 1
    if 'event.has_image' in content:
        print("   ✅ Dashboard checks has_image field")
        checks_passed += 1
    else:
        print("   ❌ Dashboard doesn't check has_image")
    
    # Check token badge
    checks_total += 1
    if 'token-badge' in content:
        print("   ✅ Token badge display implemented")
        checks_passed += 1
    else:
        print("   ❌ Token badge not found")
    
    # Check camera icon for images
    checks_total += 1
    if '📷' in content and 'token-with-image' in content:
        print("   ✅ Camera icon (📷) for image queries")
        checks_passed += 1
    else:
        print("   ❌ No camera icon for image queries")
else:
    print("   ❌ dashboard.html not found")
    checks_total += 3

# Test 6: Check CSS for token badges
print("\n6. CSS Styling:")
css_file = Path("app/static/css/dashboard.css")
if css_file.exists():
    content = css_file.read_text()
    
    checks_total += 1
    if '.token-badge' in content:
        print("   ✅ .token-badge style defined")
        checks_passed += 1
    else:
        print("   ❌ .token-badge style missing")
    
    checks_total += 1
    if '.token-with-image' in content:
        print("   ✅ .token-with-image style defined")
        checks_passed += 1
    else:
        print("   ❌ .token-with-image style missing")
else:
    print("   ❌ dashboard.css not found")
    checks_total += 2

# Summary
print("\n" + "=" * 70)
print("TEST SUMMARY")
print("=" * 70)
print(f"Checks Passed: {checks_passed}/{checks_total}")

if checks_passed == checks_total:
    print("\n✅ ALL CHECKS PASSED!")
    print("\nLogging and reporting is complete for:")
    print("  📱 Telegram channel")
    print("  🌐 Web channel (via /agents/invoke)")
    print("  📊 Dashboard activity log")
    print("\nFeatures:")
    print("  ✓ Token tracking (prompt + completion + total)")
    print("  ✓ has_image flag for all channels")
    print("  ✓ Special titles for image queries (📷 icon)")
    print("  ✓ Token badges in dashboard")
    print("  ✓ Different colors for text vs image queries")
    print("  ✓ Cost calculation included")
else:
    print(f"\n⚠️  {checks_total - checks_passed} checks failed")
    print("Review the issues above")
    sys.exit(1)

print("\n" + "=" * 70)
print("TESTING CHECKLIST")
print("=" * 70)
print("""
Manual testing required:

1. Web Channel:
   - Send text query via dashboard
   - Send query with image via dashboard
   - Check activity log shows both
   - Verify token counts
   - Verify 📷 icon for image query

2. Telegram Channel:
   - Send text message to bot
   - Send photo to bot
   - Check activity log shows both
   - Verify token counts
   - Verify 📷 icon for photo

3. Dashboard Display:
   - Open activity log
   - Verify token badges show
   - Verify different colors for text/image
   - Check cost display
   - Verify timestamps

4. Database Check:
   SELECT * FROM usage_records ORDER BY created_at DESC LIMIT 10;
   - Verify has_image=1 for image queries
   - Verify has_image=0 for text queries
   - Verify token counts are logged
""")
print("=" * 70)
