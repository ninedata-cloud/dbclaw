"""
Simple test for Bocha AI web search skill - without database
"""
import asyncio
from backend.config import get_settings


async def test_bocha_api():
    """Test Bocha AI API directly"""
    import aiohttp
    
    print("=" * 60)
    print("Testing Bocha AI Web Search API")
    print("=" * 60)
    
    # Get configuration
    settings = get_settings()
    api_key = settings.bocha_api_key
    api_url = settings.bocha_api_url
    
    print(f"\nAPI URL: {api_url}")
    print(f"API Key: {api_key[:10]}..." if api_key else "API Key: Not configured")
    
    if not api_key:
        print("\n✗ BOCHA_API_KEY not configured")
        print("  Please set BOCHA_API_KEY in .env file")
        return
    
    # Test cases
    test_cases = [
        {
            "name": "Search in Chinese",
            "query": "openGauss数据库",
            "count": 3,
            "summary": True,
            "freshness": "noLimit"
        },
        {
            "name": "Search in English",
            "query": "database performance tuning",
            "count": 3,
            "summary": True,
            "freshness": "week"
        }
    ]
    
    for test_case in test_cases:
        print(f"\n{'=' * 60}")
        print(f"Test: {test_case['name']}")
        print(f"{'=' * 60}")
        print(f"Query: {test_case['query']}")
        print(f"Count: {test_case['count']}")
        print(f"Summary: {test_case['summary']}")
        print(f"Freshness: {test_case['freshness']}")

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'query': test_case['query'],
            'count': test_case['count'],
            'summary': test_case['summary'],
            'freshness': test_case['freshness']
        }
        
        try:
            # Create connector with auto_decompress=False to handle brotli manually
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(connector=connector, auto_decompress=False) as session:
                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=25)
                ) as response:
                    print(f"\nHTTP Status: {response.status}")

                    if response.status != 200:
                        # Read raw bytes since auto_decompress is disabled
                        raw_data = await response.read()
                        content_encoding = response.headers.get('Content-Encoding', '').lower()
                        if content_encoding == 'br':
                            import brotli
                            error_text = brotli.decompress(raw_data).decode('utf-8')
                        else:
                            error_text = raw_data.decode('utf-8')
                        print(f"✗ API request failed")
                        print(f"  Error: {error_text[:200]}")
                        continue

                    # Manually handle decompression
                    raw_data = await response.read()
                    content_encoding = response.headers.get('Content-Encoding', '').lower()
                    if content_encoding == 'br':
                        import brotli
                        import json
                        decompressed_data = brotli.decompress(raw_data)
                        data = json.loads(decompressed_data.decode('utf-8'))
                    else:
                        import json
                        data = json.loads(raw_data.decode('utf-8'))

                    # Parse Bocha API response
                    if data.get('code') != 200:
                        print(f"✗ API error: {data.get('msg', 'Unknown error')}")
                        continue

                    web_pages = data.get('data', {}).get('webPages', {})
                    results = web_pages.get('value', [])
                    total_matches = web_pages.get('totalEstimatedMatches', 0)

                    print(f"✓ Search successful!")
                    print(f"  Total estimated matches: {total_matches:,}")
                    print(f"  Results returned: {len(results)}")

                    if results:
                        print(f"\n  Results:")
                        for idx, result in enumerate(results[:test_case['count']], 1):
                            print(f"    {idx}. {result.get('name', 'N/A')}")
                            print(f"       URL: {result.get('url', 'N/A')}")
                            snippet = result.get('snippet', 'N/A')
                            print(f"       Snippet: {snippet[:100]}...")
                            if test_case['summary'] and result.get('summary'):
                                summary = result.get('summary', '')
                                print(f"       Summary: {summary[:100]}...")
                            print()
                    else:
                        print("  No results returned")
        
        except aiohttp.ClientError as e:
            print(f"\n✗ Network error: {str(e)}")
        except Exception as e:
            print(f"\n✗ Unexpected error: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'=' * 60}")
    print("Test completed")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(test_bocha_api())
