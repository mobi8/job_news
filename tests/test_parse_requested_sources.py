from utils.utils import parse_requested_sources


def test_parse_requested_sources_normalizes_glassdoor_aliases():
    assert parse_requested_sources("glassdoor") == {"glassdoor_uae"}
    assert parse_requested_sources("glassdoor_uae") == {"glassdoor_uae"}


def test_parse_requested_sources_keeps_multiple_sources():
    sources = parse_requested_sources("linkedin,indeed,glassdoor")
    assert sources == {"linkedin_public", "indeed_uae", "glassdoor_uae"}


def test_parse_requested_sources_returns_none_for_empty_value():
    assert parse_requested_sources("") is None
