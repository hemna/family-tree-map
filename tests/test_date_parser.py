from app.date_parser import extract_year


def test_standard_date():
    assert extract_year("12 March 1845") == 1845


def test_iso_date():
    assert extract_year("1845-03-12") == 1845


def test_year_only():
    assert extract_year("1845") == 1845


def test_about_date():
    assert extract_year("About 1845") == 1845


def test_before_date():
    assert extract_year("Before March 1845") == 1845


def test_after_date():
    assert extract_year("After 1900") == 1900


def test_between_dates():
    assert extract_year("between 1840 and 1850") == 1840


def test_no_year():
    assert extract_year("unknown") is None


def test_empty_string():
    assert extract_year("") is None


def test_none_input():
    assert extract_year(None) is None
