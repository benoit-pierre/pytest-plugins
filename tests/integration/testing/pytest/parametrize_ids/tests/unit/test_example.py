from pkglib.testing.pytest.parametrize_ids import pytest_generate_tests  # @UnusedImport  # NOQA
import pytest


@pytest.mark.parametrize(('f', 't'), [(sum, list), (len, int)])
def test_foo(f, t):
    assert isinstance(f([[1], [2]]), t)


def test_bar():  # unparametrized
    pass
