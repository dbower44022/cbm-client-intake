from core.phone import e164_or_none, format_us, to_e164


def test_us_ten_digit_dashed():
    assert to_e164("216-555-0100") == "+12165550100"


def test_us_ten_digit_parens_spaces():
    assert to_e164("(216) 555-0100") == "+12165550100"


def test_us_eleven_digit_leading_one():
    assert to_e164("1-216-555-0100") == "+12165550100"


def test_plain_ten_digits():
    assert to_e164("2165550100") == "+12165550100"


def test_already_e164_passthrough():
    assert to_e164("+12165550100") == "+12165550100"


def test_empty_passthrough():
    assert to_e164("") == ""


# --- e164_or_none: drop implausible numbers so the CRM write isn't 400'd ---

def test_e164_or_none_keeps_valid_us_number():
    assert e164_or_none("216-555-0100") == "+12165550100"
    assert e164_or_none("2165550100") == "+12165550100"
    assert e164_or_none("+44 7911 123456") == "+447911123456"


def test_e164_or_none_drops_too_short():
    assert e164_or_none("12345") is None      # the value that sank 4501d077
    assert e164_or_none("555-0100") is None    # 7 digits


def test_e164_or_none_drops_empty_or_none():
    assert e164_or_none("") is None
    assert e164_or_none(None) is None
    assert e164_or_none("   ") is None


def test_e164_or_none_drops_too_long():
    assert e164_or_none("1234567890123456") is None  # 16 digits > E.164 max


# --- format_us: the standard US display format, (216)-555-1234 --------------

def test_format_us_from_e164():
    assert format_us("+12165550142") == "(216)-555-0142"


def test_format_us_from_ten_digits_and_punctuation():
    assert format_us("2165550142") == "(216)-555-0142"
    assert format_us("216.555.0142") == "(216)-555-0142"
    assert format_us("(216) 555-0142") == "(216)-555-0142"


def test_format_us_eleven_digit_leading_one():
    assert format_us("1-216-555-0142") == "(216)-555-0142"


def test_format_us_non_us_passthrough():
    # international / non-10-digit values are shown as-is, never mangled
    assert format_us("+447911123456") == "+447911123456"
    assert format_us("555-0100") == "555-0100"


def test_format_us_empty_passthrough():
    assert format_us("") == ""
    assert format_us(None) is None
