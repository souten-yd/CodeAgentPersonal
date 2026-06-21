from pricing import apply_discount


def test_apply_discount_fixture():
    assert apply_discount(100, 0.1) == 90
