"""
Manual test script to verify token and image logging in dashboard.
Run the server and visit the dashboard to test manually.
"""

# Instructions for manual testing:

# 1. Start the server:
#    uvicorn app.main:app --reload

# 2. Login to dashboard:
#    http://localhost:8000/dashboard

# 3. Test without image:
#    - Enter a query: "What is AI?"
#    - Click "Send Query"
#    - Check response shows:
#      ✓ Agent used: [agent_name] ([model])
#      ✓ Usage: X requests remaining
#    - Go to Usage Metrics section
#    - Check it shows:
#      ✓ Total Requests
#      ✓ Total Tokens (should be > 0)
#      ✓ Total Cost

# 4. Test with image:
#    - Click "📷 Choose Image"
#    - Select an image file
#    - Enter query: "What's in this image?"
#    - Click "Send Query"
#    - Check response shows:
#      ✓ Agent used: [agent_name] ([model]) 📷 with image
#      ✓ Usage info

# 5. Check Usage Metrics:
#    - Refresh or wait for auto-reload
#    - Total Tokens should be HIGHER now (images use more tokens)
#    - Total Cost should reflect image processing

# 6. Check Activity Log (if visible):
#    - Should show entries like:
#      "🤖 AI Agent Query • X,XXX tokens • $X.XX"
#    - Entries with images should have more tokens

# API Testing with curl:

# Test 1: Send query without image
curl -X POST http://localhost:8000/agents/invoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "What is AI?",
    "variables": {}
  }'

# Expected response includes:
# {
#   "agent_id": 1,
#   "agent_name": "...",
#   "output": "...",
#   "model": "...",
#   "processed_image": false,
#   "usage": {...},
#   "usage_tokens": 150  # example number
# }


# Test 2: Upload image
curl -X POST http://localhost:8000/web/upload-image \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@test_image.jpg"

# Expected response:
# {
#   "success": true,
#   "file_path": "media/uploads/timestamp_uuid.jpg",
#   "message": "Image uploaded successfully",
#   "file_size": 12345
# }


# Test 3: Send query with image
curl -X POST http://localhost:8000/agents/invoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "What is in this image?",
    "image_path": "media/uploads/timestamp_uuid.jpg",
    "variables": {}
  }'

# Expected response includes:
# {
#   "agent_id": 1,
#   "agent_name": "...",
#   "output": "...",
#   "model": "...",
#   "processed_image": true,
#   "usage": {...},
#   "usage_tokens": 500  # MORE tokens for images!
# }


# Test 4: Check usage stats
curl -X GET "http://localhost:8000/billing/usage?days=30" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected response:
# {
#   "from_date": "2026-01-01T...",
#   "to_date": "2026-01-31T...",
#   "requests": 2,  # 2 requests made above
#   "tokens": 650,  # 150 + 500 from both requests
#   "cost": 0.013   # calculated cost
# }


# Test 5: Check activity log
curl -X GET "http://localhost:8000/billing/activity?limit=10&days=30" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected response includes entries like:
# [
#   {
#     "id": "usage_123",
#     "type": "usage",
#     "title": "🤖 AI Agent Query",
#     "description": "Used AI agent • 500 tokens • $0.01",
#     "total_tokens": 500,
#     "cost": 0.01,
#     ...
#   },
#   {
#     "id": "usage_122",
#     "type": "usage",
#     "title": "🤖 AI Agent Query",
#     "description": "Used AI agent • 150 tokens • $0.003",
#     "total_tokens": 150,
#     "cost": 0.003,
#     ...
#   }
# ]


# Database verification:

# Check UsageRecord table:
# sqlite3 bot.db "SELECT id, endpoint, total_tokens, has_image, cost FROM usage_records ORDER BY created_at DESC LIMIT 5;"

# Expected output:
# id | endpoint           | total_tokens | has_image | cost
# ---|--------------------|--------------|-----------|------
# 5  | /agents/invoke     | 500          | 1         | 0.01
# 4  | /agents/invoke     | 150          | 0         | 0.003

# Verification checklist:
# ✓ Tokens are logged for requests without images
# ✓ Tokens are logged for requests WITH images  
# ✓ has_image=1 for image requests, 0 for text-only
# ✓ Cost is calculated correctly
# ✓ Dashboard shows token counts in Usage Metrics
# ✓ Activity log shows token information
# ✓ Images show 📷 indicator in dashboard response
# ✓ Image requests typically have MORE tokens than text-only

print(__doc__)
