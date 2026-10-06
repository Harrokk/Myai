from scripts.verify_git_history_cleanup import FORBIDDEN_BASENAMES


def test_history_cleanup_forbidden_basename_set_is_exact():
    assert FORBIDDEN_BASENAMES == {
        "memory.db",
        "__init__.cpython-314.pyc",
        "system.cpython-314.pyc",
    }
