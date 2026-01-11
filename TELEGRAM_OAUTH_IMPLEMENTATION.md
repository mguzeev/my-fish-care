# Telegram OAuth Implementation

## Overview
Implemented a complete Telegram OAuth authentication flow that allows users to register and login using their Telegram accounts, as well as link existing accounts to Telegram.

## Implementation Date
January 11, 2026

## Components Implemented

### 1. Authentication Endpoints

#### GET /auth/telegram
- Returns Telegram bot information for initiating login flow
- Response includes bot username and callback URL
- Used to start the Telegram login widget

#### POST /auth/telegram/callback
- Handles Telegram OAuth callback with user authentication data
- Verifies Telegram authentication hash using HMAC-SHA256
- Creates new user or logs in existing user based on telegram_id
- Returns JWT access and refresh tokens
- Parameters:
  - `id`: Telegram user ID (required)
  - `first_name`: User's first name (required)
  - `last_name`: User's last name (optional)
  - `username`: Telegram username (optional)
  - `photo_url`: Profile photo URL (optional)
  - `auth_date`: Authentication timestamp (required)
  - `hash`: Telegram authentication hash (required)

#### GET /auth/telegram/link
- Returns current Telegram linking status for authenticated user
- Shows whether user's account is already linked to Telegram
- Returns bot username and user ID for linking process

#### POST /auth/telegram/link
- Links a Telegram account to an existing authenticated user
- Requires valid JWT access token
- Parameter: `telegram_id` (Telegram user ID to link)
- Validates that Telegram ID is not already linked to another user

### 2. Security Implementation

#### Hash Verification Function
```python
def _verify_telegram_auth_data(data: dict) -> bool
```
- Verifies authenticity of Telegram login data
- Uses HMAC-SHA256 with bot token as secret key
- Validates data check string against provided hash
- Prevents unauthorized access and replay attacks

### 3. User Creation Logic

When a new user logs in via Telegram:
- Generates unique username: `tg_{telegram_id}` or `tg_{telegram_id}_{timestamp}`
- Creates temporary email: `tg_{telegram_id}@telegram.local`
- Sets full_name from Telegram first_name and last_name
- Stores telegram_id for future logins
- Creates secure hashed password (not used for Telegram logins)

### 4. Configuration Updates

Added to `app/core/config.py`:
- `api_base_url`: Base URL for OAuth callbacks (default: "http://localhost:8000")
- `telegram_bot_username`: Telegram bot username for login widget

### 5. Schema Updates

Updated `app/auth/schemas.py`:
- Added `telegram_id: Optional[int]` field to `UserResponse` schema
- Allows API responses to include Telegram account information

## Test Coverage

Created 6 comprehensive tests in `tests/test_auth_api.py`:

1. **test_telegram_login_new_user**
   - Tests complete new user registration via Telegram
   - Verifies hash generation and validation
   - Confirms JWT token generation

2. **test_telegram_login_existing_user**
   - Tests login with existing Telegram-registered user
   - Verifies existing user recognition by telegram_id

3. **test_telegram_login_invalid_hash**
   - Tests security by attempting login with invalid hash
   - Confirms rejection with 401 Unauthorized

4. **test_telegram_link_account**
   - Tests linking Telegram to existing email/password account
   - Verifies telegram_id is properly stored

5. **test_telegram_get_link_status_linked**
   - Tests status endpoint when account is linked
   - Confirms proper response format

6. **test_telegram_get_link_status_not_linked**
   - Tests status endpoint when account is not linked
   - Verifies correct unlinked status

## Test Results
- Total tests: 56 (50 existing + 6 new)
- All tests passing: ✅
- Coverage: Complete OAuth flow, security validation, edge cases

## Files Modified

1. `app/auth/router.py` (+242 lines)
   - Added 4 new endpoints
   - Added hash verification function
   - Integrated with existing auth system

2. `app/core/config.py` (+2 settings)
   - Added api_base_url
   - Added telegram_bot_username

3. `app/auth/schemas.py` (+1 field)
   - Added telegram_id to UserResponse

4. `tests/test_auth_api.py` (+205 lines)
   - Added 6 comprehensive tests
   - Covers all new endpoints and security

## Integration with Existing System

### Database
- Uses existing `User.telegram_id` field (already present in model)
- Fully compatible with existing user management
- No migrations required

### Authentication
- Integrates seamlessly with existing JWT token system
- Uses same `create_access_token()` and `create_refresh_token()` functions
- Compatible with existing auth middleware

### Landing Page
- Templates already reference `/auth/telegram` endpoint
- Ready for Telegram Login Widget integration
- No template changes needed

## Security Features

1. **HMAC-SHA256 Verification**
   - Validates all incoming Telegram auth data
   - Prevents tampering and unauthorized access

2. **Unique User Constraints**
   - telegram_id is unique in database
   - Prevents duplicate Telegram account linking
   - Validates against existing users

3. **JWT Token Security**
   - Uses existing secure token generation
   - Standard expiration times (30 min access, 7 day refresh)
   - Follows OAuth2 bearer token pattern

## Usage Example

### 1. Login via Telegram (New User)
```bash
POST /auth/telegram/callback?id=123456789&first_name=John&last_name=Doe&username=johndoe&auth_date=1234567890&hash=abc123...

Response:
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### 2. Check Link Status
```bash
GET /auth/telegram/link
Authorization: Bearer eyJ...

Response:
{
  "status": "not_linked",
  "bot_username": "mybot",
  "user_id": 1
}
```

### 3. Link Telegram to Existing Account
```bash
POST /auth/telegram/link?telegram_id=123456789
Authorization: Bearer eyJ...

Response:
{
  "id": 1,
  "email": "user@example.com",
  "username": "user",
  "telegram_id": 123456789,
  ...
}
```

## Next Steps (Optional Enhancements)

1. **Telegram Login Widget Integration**
   - Add Telegram Login Widget JavaScript to landing page
   - Configure widget with bot username
   - Handle client-side redirect to callback URL

2. **Google OAuth Implementation**
   - Follow similar pattern as Telegram OAuth
   - Use Google OAuth 2.0 flow
   - Add google_id field to User model

3. **Apple OAuth Implementation**
   - Implement Sign in with Apple
   - Handle Apple-specific token format
   - Add apple_id field to User model

4. **Enhanced Telegram Integration**
   - Sync profile photos from Telegram
   - Store additional Telegram user metadata
   - Implement Telegram Mini App authentication

## Performance Considerations

- Hash verification is fast (HMAC-SHA256)
- Single database query for user lookup
- Efficient user creation with minimal fields
- No external API calls during callback

## Backwards Compatibility

- Fully backwards compatible with existing auth system
- Does not affect email/password authentication
- Existing users can add Telegram login via linking
- No breaking changes to existing endpoints

## Documentation

- All endpoints documented with docstrings
- Type hints for all parameters
- Clear error messages for validation failures
- Logging for security events (new registrations, linking)

## Conclusion

The Telegram OAuth implementation provides a secure, tested, and production-ready authentication method that seamlessly integrates with the existing system. All 56 tests pass, including 6 new comprehensive tests covering the complete Telegram OAuth flow.
