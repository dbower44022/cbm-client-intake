from core.phone import to_e164


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
