from contract import parse_token


def test_parse_token_contract():
    assert parse_token("x") == "x"
