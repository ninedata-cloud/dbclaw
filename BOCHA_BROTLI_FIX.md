# Bocha Web Search Brotli Decompression Fix

## Problem

The Bocha AI web search skill was failing with the error:
```
400, message: Can not decode content-encoding: br
```

## Root Cause

The issue was caused by an incompatibility between:
- **Python 3.13** 
- **aiohttp 3.13.3**
- **brotli/brotlipy** libraries

The Bocha API returns responses with Brotli (br) compression. aiohttp attempts to automatically decompress responses, but:

1. The `brotli` package (versions 1.1.0 and 1.2.0) provides a `Decompressor` class with a `process()` method, not `decompress()`
2. aiohttp expects a `decompress(data, max_length)` method with 2 arguments
3. The `brotlipy` package provides `decompress(data)` with only 1 argument
4. This mismatch causes aiohttp's automatic decompression to fail

## Solution

Disable aiohttp's automatic decompression and handle Brotli decompression manually:

```python
# Create session with auto_decompress=False
connector = aiohttp.TCPConnector()
async with aiohttp.ClientSession(connector=connector, auto_decompress=False) as session:
    async with session.post(url, json=payload, headers=headers) as response:
        # Read raw compressed data
        raw_data = await response.read()
        
        # Check content encoding
        content_encoding = response.headers.get('Content-Encoding', '').lower()
        
        # Manually decompress if needed
        if content_encoding == 'br':
            import brotli
            import json
            decompressed_data = brotli.decompress(raw_data)
            data = json.loads(decompressed_data.decode('utf-8'))
        else:
            import json
            data = json.loads(raw_data.decode('utf-8'))
```

## Files Modified

1. **backend/skills/builtin/web_search_bocha.yaml**
   - Added `auto_decompress=False` to ClientSession
   - Implemented manual Brotli decompression
   - Handles both compressed (br) and uncompressed responses

2. **test_bocha_search_simple.py**
   - Updated test script with the same fix for verification

## Dependencies

The fix requires the `brotlipy` package (already installed):
```bash
pip install brotlipy
```

Note: The `brotli` package (capital B) does NOT work due to API incompatibility.

## Testing

```bash
python test_bocha_search_simple.py
```

Expected output:
```
Status: 200
Content-Encoding: br
✓ Success! API returned N results
```

## Compatibility

- ✅ Python 3.13
- ✅ aiohttp 3.13.3
- ✅ brotlipy 0.7.0
- ✅ Works with both Brotli-compressed and uncompressed responses

## Future Considerations

This issue may be resolved in future versions of aiohttp or brotli. Monitor:
- https://github.com/aio-libs/aiohttp/issues (aiohttp Brotli support)
- https://github.com/google/brotli/issues (brotli Python bindings)

For now, manual decompression is the most reliable solution.
