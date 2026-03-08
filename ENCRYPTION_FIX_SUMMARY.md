# API Key Encryption Fix Summary

## Problem
Scheduled reports were failing with `InvalidToken` error when trying to decrypt API keys. The error occurred because:

1. The `.env` file had `encryption_key` (lowercase) instead of `ENCRYPTION_KEY` (uppercase)
2. The API keys in the database were encrypted with a different/unknown encryption key
3. When the code tried to decrypt with the current key, it failed

## Root Cause
- Environment variable naming mismatch: `encryption_key` vs `ENCRYPTION_KEY`
- API keys were encrypted with a previous encryption key that was lost or changed
- Pydantic Settings requires exact case match for environment variables

## Solution Applied

### 1. Fixed Environment Variable (`.env`)
Changed:
```
encryption_key=8xjFTVTFnB2RXJYLWA7TKLHkvfYhtpHfEPOyEtZmAaA=
```

To:
```
ENCRYPTION_KEY=8xjFTVTFnB2RXJYLWA7TKLHkvfYhtpHfEPOyEtZmAaA=
```

### 2. Re-encrypted API Keys
Since the old encryption key was unknown, we:
1. Cleared the old encrypted API keys
2. Re-encrypted them with the correct encryption key from `.env`
3. Used the API keys from the `.env` file:
   - `qwen-plus`: sk-156b463e041340f781305dec2e254dd3
   - `qwen3.5-plus`: sk-56d9e30b5236471099cbc3a8c63c7821

### 3. Created Utility Scripts

**fix_encryption.py** - Diagnostic tool with commands:
- `test` - Test if API keys can be decrypted
- `clear` - Clear all encrypted API keys
- `reencrypt KEY` - Re-encrypt with old key if known

**fix_encryption_auto.py** - Automatically clear encrypted keys

**set_api_keys.py** - Set API keys with proper encryption

## Verification

All API keys now decrypt successfully:
```
✓ Model 1 (qwen-plus): Successfully decrypted
✓ Model 2 (qwen3.5-plus): Successfully decrypted
```

## Testing Required

1. Restart the backend server to pick up the fixed `ENCRYPTION_KEY`
2. Trigger a scheduled report to verify it works without `InvalidToken` error
3. Test AI diagnosis features that use the API keys

## Prevention

- Always use uppercase `ENCRYPTION_KEY` in `.env` file
- Keep the encryption key consistent across deployments
- If changing the encryption key, use `fix_encryption.py reencrypt` to migrate existing keys
- Never commit `.env` file to git (already in `.gitignore`)

## Files Modified

- `.env` - Fixed environment variable name
- `data/smartdba.db` - Re-encrypted API keys in `ai_models` table

## Files Created

- `fix_encryption.py` - Encryption diagnostic and fix tool
- `fix_encryption_auto.py` - Auto-clear encrypted keys
- `set_api_keys.py` - Set API keys with proper encryption
- `ENCRYPTION_FIX_SUMMARY.md` - This document
