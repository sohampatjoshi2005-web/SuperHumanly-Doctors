import httpx
import time
import asyncio
import json

async def test_performance():
    base_url = "http://localhost:8001"
    
    # 1. Login
    login_data = {
        "username": "admin",
        "email": "admin@superhumanlydoctors.io",
        "password": "SovereignAdmin2026!"
    }
    
    async with httpx.AsyncClient() as client:
        print("🚀 Logging in...")
        resp = await client.post(f"{base_url}/v1/auth/login", json=login_data)
        if resp.status_code != 200:
            print(f"❌ Login failed: {resp.text}")
            return
        
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Test Intelligence Query
        query_payload = {
            "query": "Show me the top medications prescribed in the last 30 days"
        }
        
        print(f"📡 Sending query: {query_payload['query']}")
        start_time = time.time()
        ttfb = None
        
        async with client.stream("POST", f"{base_url}/v1/intelligence/query", json=query_payload, headers=headers, timeout=60.0) as response:
            async for line in response.aiter_lines():
                if not ttfb:
                    ttfb = time.time() - start_time
                    print(f"⏱️ Time To First Byte (TTFB): {ttfb:.4f}s")
                
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data["type"] == "done":
                        break
        
        total_time = time.time() - start_time
        print(f"✅ Total Response Time: {total_time:.4f}s")

if __name__ == "__main__":
    asyncio.run(test_performance())
