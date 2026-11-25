import pytest

from termscheck.screens import run_screens
from termscheck.synthetic import generate, to_screen_input


@pytest.fixture(scope="session")
def dataset():
    return generate()


@pytest.fixture(scope="session")
def screen_result(dataset):
    return run_screens(to_screen_input(dataset))
