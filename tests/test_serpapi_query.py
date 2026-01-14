"""SerpAPI query builder tests.

These tests focus on deterministic, pure helpers used by the recommendation pipeline.
"""

from src.email_agent import _build_preference_context, _build_serpapi_search_query


def test_build_serpapi_search_query_uses_structured_finance_fields():
    preferences = {
        "target_role_titles": ["Investment Banking Analyst", "Investment Banking Associate"],
        "bank_tier": "BB",
        "group": "M&A; ECM",
        "sector": "TMT; Healthcare",
        "location": "New York; London",
    }

    query = _build_serpapi_search_query(preferences, field="Finance", purpose="Finance career opportunities")

    assert "site:linkedin.com/in/" in query
    assert '"Investment Banking Analyst"' in query
    assert '"Investment Banking Associate"' in query
    assert '"Goldman Sachs"' in query  # from bank_tier=BB mapping
    assert '"M&A"' in query
    assert '"ECM"' in query
    assert '"TMT"' in query
    assert '"Healthcare"' in query
    assert '"New York"' in query


def test_build_serpapi_search_query_does_not_add_bank_tier_firms_when_must_have_present():
    preferences = {
        "must_have": "Blackstone",
        "bank_tier": "BB",
    }
    query = _build_serpapi_search_query(preferences, field="Finance", purpose="Finance career opportunities")

    assert '"Blackstone"' in query
    assert "Goldman Sachs" not in query


def test_build_preference_context_formats_list_and_dict_fields():
    preferences = {
        "track": "finance",
        "contact_channels": ["linkedin", "email"],
        "target_role_titles": ["Analyst", "Associate"],
        "recruiting_context": {"role_type": "SA", "timeline": "2026", "notes": "Summer analyst"},
    }
    context = _build_preference_context(preferences)

    assert "Targeting preferences:" in context
    assert "Preferred contact channels" in context
    assert "linkedin" in context and "email" in context
    assert "Recruiting context" in context
    assert '"role_type": "SA"' in context

