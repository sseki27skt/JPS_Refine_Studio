import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "modules")))
from rule_filter import match_about_keyword

def test_match_about_keyword_empty_inputs():
    """Test with empty or None inputs."""
    assert match_about_keyword("", "target") == False
    assert match_about_keyword("keyword", "") == False
    assert match_about_keyword(None, "target") == False
    assert match_about_keyword("keyword", None) == False
    assert match_about_keyword("", "") == False
    assert match_about_keyword(None, None) == False

def test_match_about_keyword_exact_match():
    """Test exact string matching with and without whitespace."""
    assert match_about_keyword("exact_match", "exact_match") == True
    assert match_about_keyword(" exact_match ", "exact_match") == True
    assert match_about_keyword("exact_match", " exact_match ") == True
    assert match_about_keyword("exact_match", "different") == False

def test_match_about_keyword_ndc_matching():
    """Test NDC code hierarchical matching."""
    # Exact code matching
    assert match_about_keyword("768", "768") == True
    assert match_about_keyword("ndc9:768", "768") == True
    assert match_about_keyword("768.1", "768.1") == True

    # Hierarchical inclusion (rule '76' / '760' matches '768.1')
    assert match_about_keyword("768", "76") == True
    assert match_about_keyword("768.1", "76") == True
    assert match_about_keyword("768", "760") == True
    assert match_about_keyword("768.1", "760") == True
    assert match_about_keyword("ndc9:768.1", "76") == True

    # Non-matches
    assert match_about_keyword("976", "76") == False
    assert match_about_keyword("76", "768") == False
    assert match_about_keyword("768", "769") == False

def test_match_about_keyword_hierarchical_separators():
    """Test hierarchical separator matching ('--', ' / ', ' : ', '･', '・')."""
    # Exact match on first part
    assert match_about_keyword("History--Japan", "History") == True
    assert match_about_keyword("History / Japan", "History") == True
    assert match_about_keyword("History : Japan", "History") == True
    assert match_about_keyword("History･Japan", "History") == True
    assert match_about_keyword("History・Japan", "History") == True

    # Exact match on any part
    assert match_about_keyword("History--Japan--Tokyo", "Japan") == True
    assert match_about_keyword("History / Japan / Tokyo", "Tokyo") == True

    # Not matching part
    assert match_about_keyword("History--Japan", "Europe") == False

def test_match_about_keyword_partial_match_fallback():
    """Test partial match fallback (rule >= 3 characters)."""
    assert match_about_keyword("long_keyword_string", "keyword") == True
    assert match_about_keyword("long_keyword_string", "key") == True

    # Less than 3 characters should not fallback to partial match
    assert match_about_keyword("long_keyword_string", "ke") == False

    # No match
    assert match_about_keyword("long_keyword_string", "apple") == False

def test_match_about_keyword_whitespace_handling():
    """Test that keywords and targets are stripped before matching."""
    assert match_about_keyword(" keyword ", " keyword ") == True
    assert match_about_keyword(" keyword ", "keyword") == True
    assert match_about_keyword("keyword", " keyword ") == True
    assert match_about_keyword(" keyword--test ", "keyword") == True
