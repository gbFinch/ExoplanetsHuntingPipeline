from exohunt.cli import _safe_target_name


def test_safe_target_name():
    assert _safe_target_name("TIC 261136679") == "tic_261136679"
