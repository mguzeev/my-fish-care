# Google OAuth Integration Guide

## Overview

This project now supports Google OAuth authentication, allowing users to register and login using their Google accounts.

## Features

- ✅ Sign in with Google
- ✅ Automatic user registration on first login
- ✅ Email verification from Google
- ✅ Profile picture sync
- ✅ Seamless integration with existing user system
- ✅ Support for both OAuth and traditional password-based authentication

## Setup Instructions

### 1. Create Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google+ API:
   - Go to "APIs & Services" > "Library"
   - Search for "Google+ API" and enable it
4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth 2.0 Client ID"
   - Choose "Web application"
   - Add authorized redirect URIs:
     - For local development: `http://localhost:8000/auth/google/callback`
     - For production: `https://yourdomain.com/auth/google/callback`
   - Save and copy the Client ID and Client Secret

### 2. Configure Environment Variables

Add the following variables to your `.env.local` or `.env` file:

```bash
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-google-client-id-here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret-here

# API Base URL (used for OAuth redirect URI)
API_BASE_URL=http://localhost:8000  # or your production URL
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

New dependencies added:
- `authlib==1.3.0` - OAuth client library
- `itsdangerous==2.1.2` - Security utilities

### 4. Run Database Migration

```bash
alembic upgrade head
```

This will add the following fields to the `users` table:
- `oauth_provider` - OAuth provider name (e.g., 'google')
- `oauth_id` - OAuth provider's user ID
- `picture_url` - User's profile picture URL

### 5. Test the Integration

1. Start the development server:
```bash
uvicorn app.main:app --reload
```

2. Open the test page:
```
http://localhost:8000/static/google_oauth_test.html
```

3. Click "Sign in with Google" and complete the OAuth flow

## API Endpoints

### Initiate Google OAuth Login
```
GET /auth/google/login
```
Redirects to Google's OAuth authorization page.

### OAuth Callback (handled automatically)
```
GET /auth/google/callback
```
Processes the OAuth callback from Google and creates/updates user account.

Returns a redirect to the frontend with tokens:
```
/auth/callback?access_token=xxx&refresh_token=yyy
```

## User Flow

### New User Registration via Google

1. User clicks "Sign in with Google"
2. User authorizes the application on Google
3. System receives user information from Google
4. New user account is created with:
   - Email from Google
   - Auto-generated username from email
   - Full name from Google profile
   - Profile picture URL
   - Email automatically verified
   - OAuth provider set to 'google'
5. Default organization and billing account created
6. Access and refresh tokens returned
7. User redirected to frontend with tokens

### Existing User Login via Google

1. User clicks "Sign in with Google"
2. System matches user by Google ID or email
3. OAuth information updated if needed
4. Last login timestamp updated
5. Access and refresh tokens returned
6. User redirected to frontend with tokens

## Security Considerations

- OAuth users don't have passwords stored in the database
- Email addresses from Google are automatically verified
- Users who registered with email/password cannot login via Google OAuth (accounts are kept separate to prevent account takeover)
- Use HTTPS in production for secure token transmission
- Tokens should be stored securely in the frontend (e.g., httpOnly cookies)

## Frontend Integration

The callback redirects to:
```
{API_BASE_URL}/auth/callback?access_token=xxx&refresh_token=yyy
```

Your frontend should:
1. Parse the tokens from URL parameters
2. Store them securely (localStorage, sessionStorage, or httpOnly cookies)
3. Use the access token for API requests
4. Use the refresh token to get new access tokens when needed

Example JavaScript:
```javascript
const urlParams = new URLSearchParams(window.location.search);
const accessToken = urlParams.get('access_token');
const refreshToken = urlParams.get('refresh_token');

if (accessToken && refreshToken) {
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
    // Redirect to dashboard or home page
    window.location.href = '/dashboard';
}
```

## Error Handling

Common errors:
- `501 NOT IMPLEMENTED` - Google OAuth credentials not configured
- `400 BAD REQUEST` - OAuth error (invalid credentials, user denied access)
- `500 INTERNAL SERVER ERROR` - Server error during authentication

## Database Schema Changes

New fields in `users` table:
- `oauth_provider` (VARCHAR 50, nullable) - OAuth provider identifier
- `oauth_id` (VARCHAR 255, nullable, indexed) - Provider's user ID
- `picture_url` (VARCHAR 500, nullable) - Profile picture URL
- `hashed_password` - Now nullable (OAuth users don't need passwords)

## Testing Checklist

- [ ] Configure Google OAuth credentials
- [ ] Set environment variables
- [ ] Run database migration
- [ ] Test new user registration via Google
- [ ] Test existing user login via Google
- [ ] Test email/password login still works
- [ ] Verify tokens are returned correctly
- [ ] Check user profile includes Google data
- [ ] Test error cases (invalid credentials, denied access)

## Production Deployment

1. Create OAuth credentials for production domain
2. Update environment variables with production values
3. Ensure HTTPS is enabled
4. Update `API_BASE_URL` to production URL
5. Configure proper CORS settings
6. Test OAuth flow in production environment

## Troubleshooting

### Redirect URI mismatch
- Ensure the redirect URI in Google Console exactly matches your callback URL
- Check that `API_BASE_URL` is set correctly

### OAuth credentials not found
- Verify environment variables are loaded correctly
- Check that `.env` or `.env.local` file exists and is in the correct location

### User already exists error
- This shouldn't happen as the system handles existing users
- If it does, check the user matching logic in the callback handler

## Additional OAuth Providers

The system is designed to support multiple OAuth providers. To add more providers (Facebook, GitHub, etc.):

1. Register the provider in `app/auth/oauth.py`
2. Add configuration to `app/core/config.py`
3. Create similar login/callback routes in `app/auth/router.py`
4. Update frontend to show additional login buttons
