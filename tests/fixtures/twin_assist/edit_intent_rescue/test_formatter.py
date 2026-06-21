from formatter import render


def test_render_fixture():
    assert render("x") == "x"
