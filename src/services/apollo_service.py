"""Apollo.io API Service - People enrichment and email lookup.

This service handles:
- People enrichment (find email addresses)
- People search

API Documentation: https://docs.apollo.io/reference/people-api-search
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional
import requests

# Apollo API configuration
APOLLO_API_BASE = "https://api.apollo.io/api/v1"
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "zE5e5LIohNr5PDIcEYnntQ")


@dataclass
class ApolloEnrichmentResult:
    """Result from Apollo People Enrichment API."""
    success: bool
    email: Optional[str]
    email_status: Optional[str]  # verified, unverified, etc.
    first_name: Optional[str]
    last_name: Optional[str]
    title: Optional[str]
    organization: Optional[str]
    linkedin_url: Optional[str]
    phone: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    raw_data: dict
    error: Optional[str]

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "email": self.email,
            "email_status": self.email_status,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "title": self.title,
            "organization": self.organization,
            "linkedin_url": self.linkedin_url,
            "phone": self.phone,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "error": self.error,
        }


class ApolloServiceError(Exception):
    """Raised when Apollo API call fails."""
    pass


class ApolloService:
    """Apollo.io API service for people enrichment."""

    def __init__(self, api_key: str = APOLLO_API_KEY):
        self.api_key = api_key
        self.base_url = APOLLO_API_BASE

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Make authenticated request to Apollo API."""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.api_key,
        }

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=30)
            else:
                response = requests.post(url, headers=headers, json=data, timeout=30)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else 500
            try:
                error_data = e.response.json() if e.response else {}
                error_msg = error_data.get("error", str(e))
            except Exception:
                error_msg = str(e)
            raise ApolloServiceError(f"Apollo API error ({status}): {error_msg}")

        except requests.exceptions.RequestException as e:
            raise ApolloServiceError(f"Apollo API request failed: {e}")

    def enrich_person(
        self,
        *,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        name: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        organization_name: Optional[str] = None,
        domain: Optional[str] = None,
        email: Optional[str] = None,
    ) -> ApolloEnrichmentResult:
        """
        Enrich a person's data to find their email address.
        
        You need at least one of:
        - linkedin_url
        - email
        - first_name + last_name + (organization_name or domain)
        
        This endpoint costs 1 credit per successful enrichment.
        
        Args:
            first_name: Person's first name
            last_name: Person's last name
            name: Full name (will be split into first/last if provided)
            linkedin_url: LinkedIn profile URL
            organization_name: Current company name
            domain: Company domain (e.g., "google.com")
            email: Email address (for enrichment without finding email)
            
        Returns:
            ApolloEnrichmentResult with email and other enriched data
        """
        # Parse full name if provided
        if name and not (first_name and last_name):
            parts = name.strip().split()
            if len(parts) >= 2:
                first_name = parts[0]
                last_name = " ".join(parts[1:])
            elif len(parts) == 1:
                first_name = parts[0]
                last_name = ""

        # Build request data
        data: dict[str, Any] = {}

        if first_name:
            data["first_name"] = first_name
        if last_name:
            data["last_name"] = last_name
        if linkedin_url:
            # Clean up LinkedIn URL
            if "/in/" in linkedin_url:
                data["linkedin_url"] = linkedin_url
        if organization_name:
            data["organization_name"] = organization_name
        if domain:
            data["domain"] = domain
        if email:
            data["email"] = email

        # Validate we have enough data
        has_linkedin = "linkedin_url" in data
        has_email = "email" in data
        has_name_org = (
            "first_name" in data
            and "last_name" in data
            and ("organization_name" in data or "domain" in data)
        )

        if not (has_linkedin or has_email or has_name_org):
            return ApolloEnrichmentResult(
                success=False,
                email=None,
                email_status=None,
                first_name=first_name,
                last_name=last_name,
                title=None,
                organization=organization_name,
                linkedin_url=linkedin_url,
                phone=None,
                city=None,
                state=None,
                country=None,
                raw_data={},
                error="Insufficient data: Need LinkedIn URL, email, or name + organization",
            )

        try:
            result = self._make_request("POST", "people/match", data=data)
            person = result.get("person", {})

            if not person:
                return ApolloEnrichmentResult(
                    success=False,
                    email=None,
                    email_status=None,
                    first_name=first_name,
                    last_name=last_name,
                    title=None,
                    organization=organization_name,
                    linkedin_url=linkedin_url,
                    phone=None,
                    city=None,
                    state=None,
                    country=None,
                    raw_data=result,
                    error="No matching person found in Apollo database",
                )

            # Extract email
            found_email = person.get("email")
            email_status = person.get("email_status")
            
            # Extract organization
            org = person.get("organization", {})
            org_name = org.get("name") if isinstance(org, dict) else None

            return ApolloEnrichmentResult(
                success=bool(found_email),
                email=found_email,
                email_status=email_status,
                first_name=person.get("first_name"),
                last_name=person.get("last_name"),
                title=person.get("title"),
                organization=org_name,
                linkedin_url=person.get("linkedin_url"),
                phone=person.get("phone_numbers", [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
                city=person.get("city"),
                state=person.get("state"),
                country=person.get("country"),
                raw_data=person,
                error=None if found_email else "Email not found in Apollo database",
            )

        except ApolloServiceError as e:
            return ApolloEnrichmentResult(
                success=False,
                email=None,
                email_status=None,
                first_name=first_name,
                last_name=last_name,
                title=None,
                organization=organization_name,
                linkedin_url=linkedin_url,
                phone=None,
                city=None,
                state=None,
                country=None,
                raw_data={},
                error=str(e),
            )

    def search_people(
        self,
        *,
        person_titles: Optional[list[str]] = None,
        person_seniorities: Optional[list[str]] = None,
        person_locations: Optional[list[str]] = None,
        organization_locations: Optional[list[str]] = None,
        q_organization_domains: Optional[list[str]] = None,
        organization_num_employees_ranges: Optional[list[str]] = None,
        q_keywords: Optional[str] = None,
        page: int = 1,
        per_page: int = 10,
    ) -> list[dict]:
        """
        Search for people in Apollo database.
        
        This endpoint does NOT consume credits and does NOT return emails.
        Use enrich_person() to get email addresses.
        
        Args:
            person_titles: Job titles to search for
            person_seniorities: Seniority levels (owner, founder, c_suite, vp, director, manager, senior, entry, intern)
            person_locations: Where people live
            organization_locations: Company HQ locations
            q_organization_domains: Company domains
            organization_num_employees_ranges: Employee count ranges (e.g., "1,10", "100,500")
            q_keywords: Keyword search
            page: Page number
            per_page: Results per page (max 100)
            
        Returns:
            List of people (without emails)
        """
        data: dict[str, Any] = {
            "page": page,
            "per_page": min(per_page, 100),
        }

        if person_titles:
            data["person_titles"] = person_titles
        if person_seniorities:
            data["person_seniorities"] = person_seniorities
        if person_locations:
            data["person_locations"] = person_locations
        if organization_locations:
            data["organization_locations"] = organization_locations
        if q_organization_domains:
            data["q_organization_domains_list"] = q_organization_domains
        if organization_num_employees_ranges:
            data["organization_num_employees_ranges"] = organization_num_employees_ranges
        if q_keywords:
            data["q_keywords"] = q_keywords

        try:
            result = self._make_request("POST", "mixed_people/search", data=data)
            return result.get("people", [])
        except ApolloServiceError:
            return []

    def lookup_email_by_linkedin(self, linkedin_url: str) -> ApolloEnrichmentResult:
        """
        Convenience method to look up email by LinkedIn URL only.
        
        Args:
            linkedin_url: Full LinkedIn profile URL
            
        Returns:
            ApolloEnrichmentResult with email if found
        """
        return self.enrich_person(linkedin_url=linkedin_url)

    def lookup_email_by_name_company(
        self,
        name: str,
        company: str,
    ) -> ApolloEnrichmentResult:
        """
        Convenience method to look up email by name and company.
        
        Args:
            name: Full name
            company: Company name
            
        Returns:
            ApolloEnrichmentResult with email if found
        """
        return self.enrich_person(name=name, organization_name=company)


# Global instance
apollo_service = ApolloService()


def lookup_contact_email(
    name: str,
    linkedin_url: Optional[str] = None,
    company: Optional[str] = None,
) -> ApolloEnrichmentResult:
    """
    Look up a contact's email using Apollo.io.
    
    Tries LinkedIn URL first (most accurate), then falls back to name + company.
    
    Args:
        name: Contact's full name
        linkedin_url: LinkedIn profile URL (preferred)
        company: Company name (fallback)
        
    Returns:
        ApolloEnrichmentResult with email if found
    """
    # Try LinkedIn URL first (most reliable)
    if linkedin_url and "/in/" in linkedin_url:
        result = apollo_service.lookup_email_by_linkedin(linkedin_url)
        if result.success:
            return result

    # Fall back to name + company
    if name and company:
        result = apollo_service.lookup_email_by_name_company(name, company)
        if result.success:
            return result

    # Last resort: just try with name and LinkedIn
    if name:
        return apollo_service.enrich_person(name=name, linkedin_url=linkedin_url)

    return ApolloEnrichmentResult(
        success=False,
        email=None,
        email_status=None,
        first_name=None,
        last_name=None,
        title=None,
        organization=company,
        linkedin_url=linkedin_url,
        phone=None,
        city=None,
        state=None,
        country=None,
        raw_data={},
        error="No sufficient information provided to look up email",
    )
