"""Quick test script for Apollo API integration."""

import os
import sys

# Set API keys
os.environ["APOLLO_API_KEY"] = "zE5e5LIohNr5PDIcEYnntQ"

from src.services.apollo_service import lookup_contact_email

def test_case(name: str, linkedin_url: str = None, company: str = None):
    """Test a single case."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"LinkedIn: {linkedin_url}")
    print(f"Company: {company}")
    print(f"{'='*60}")
    
    result = lookup_contact_email(
        name=name,
        linkedin_url=linkedin_url,
        company=company
    )
    
    print(f"\n✅ Success: {result.success}")
    if result.success:
        print(f"📧 Email: {result.email}")
        print(f"📊 Status: {result.email_status}")
        print(f"👤 Name: {result.first_name} {result.last_name}")
        print(f"🏢 Company: {result.organization}")
        print(f"💼 Title: {result.title}")
    else:
        print(f"❌ Error: {result.error}")
    
    return result


if __name__ == "__main__":
    print("\n🚀 Apollo API Quick Test\n")
    
    # Test 1: Real LinkedIn profile (Elon Musk - public figure)
    test_case(
        name="Elon Musk",
        linkedin_url="https://www.linkedin.com/in/elonmusk",
        company="Tesla"
    )
    
    # Test 2: Name + Company only
    test_case(
        name="Tim Cook",
        company="Apple"
    )
    
    # Test 3: Your test case (change to real person for testing)
    test_case(
        name="Alex Tan",
        linkedin_url="https://www.linkedin.com/in/alex-tan-ib",
        company="Goldman Sachs"
    )
    
    print(f"\n{'='*60}")
    print("✅ All tests completed!")
    print(f"{'='*60}\n")
