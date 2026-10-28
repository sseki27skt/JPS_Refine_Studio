import pytest
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "components")))
from ndc_utils import extract_ndc_number

def test_extract_ndc_number_happy_path():
    # Basic numbers
    assert extract_ndc_number("768") == "768"
    assert extract_ndc_number("768.1") == "768.1"
    assert extract_ndc_number("001") == "001"
    assert extract_ndc_number("999.99") == "999.99"
    assert extract_ndc_number("1") == "1"
    assert extract_ndc_number("12") == "12"

def test_extract_ndc_number_with_prefixes():
    # Various valid prefixes
    assert extract_ndc_number("ndc:768") == "768"
    assert extract_ndc_number("ndc9:768.1") == "768.1"
    assert extract_ndc_number("ndc10:001") == "001"
    assert extract_ndc_number("ndc#768") == "768"
    assert extract_ndc_number("ndc/768") == "768"
    assert extract_ndc_number("ndc_768") == "768"
    assert extract_ndc_number("ndc 768") == "768"

    # Case insensitive
    assert extract_ndc_number("NDC:768") == "768"
    assert extract_ndc_number("NdC9:768") == "768"

def test_extract_ndc_number_edge_cases():
    # Spaces around the number
    assert extract_ndc_number("  768.1  ") == "768.1"
    assert extract_ndc_number("\t768\n") == "768"

    # Spaces between prefix and number
    assert extract_ndc_number("ndc9: 768.1") == "768.1"
    assert extract_ndc_number("ndc:  768") == "768"

def test_extract_ndc_number_invalid_inputs():
    # None and empty string
    assert extract_ndc_number(None) is None
    assert extract_ndc_number("") is None
    assert extract_ndc_number("   ") is None

    # Incorrect types
    assert extract_ndc_number(123) is None
    assert extract_ndc_number(["768"]) is None

    # Invalid formats
    assert extract_ndc_number("invalid") is None
    assert extract_ndc_number("ndc:invalid") is None

    # NDC should be 1-3 digits before decimal
    assert extract_ndc_number("1234") is None
    assert extract_ndc_number("ndc:1234") is None

    # Text appended to the number
    assert extract_ndc_number("768abc") is None
    assert extract_ndc_number("768.1.1") is None
