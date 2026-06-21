from service import User


def test_user_fixture():
    assert User("A", "B").first == "A"
