"""Test which Apollo API endpoints work with free plan."""

import os
import requests

APOLLO_API_KEY = "zE5e5LIohNr5PDIcEYnntQ"
BASE_URL = "https://api.apollo.io/api/v1"

def test_endpoint(name: str, endpoint: str, method: str = "POST", data: dict = None):
    """Test a single API endpoint."""
    url = f"{BASE_URL}/{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": APOLLO_API_KEY,
    }
    
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"Endpoint: {endpoint}")
    print(f"Method: {method}")
    print(f"{'='*60}")
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        else:
            response = requests.post(url, headers=headers, json=data or {}, timeout=10)
        
        print(f"✅ Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"✅ SUCCESS - This endpoint works!")
            result = response.json()
            print(f"Response keys: {list(result.keys())}")
        elif response.status_code == 403:
            error_data = response.json()
            print(f"❌ FORBIDDEN: {error_data.get('error')}")
        else:
            print(f"Response: {response.text[:200]}")
            
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("\n🔍 Testing Apollo API Free Plan Endpoints\n")
    
    # Test different endpoints
    test_endpoint(
        "People Search (Basic)",
        "mixed_people/search",
        data={"page": 1, "per_page": 1}
    )
    
    test_endpoint(
        "People Match",
        "people/match",
        data={"first_name": "Test", "last_name": "User"}
    )
    
    test_endpoint(
        "Email Finder",
        "people/match",
        data={"email": "test@example.com"}
    )
    
    test_endpoint(
        "Organizations Search",
        "organizations/search",
        data={"page": 1, "per_page": 1}
    )
    
    test_endpoint(
        "Account Info",
        "auth/health",
        method="GET"
    )
    
    print(f"\n{'='*60}")
    print("Testing completed!")
    print(f"{'='*60}\n")
