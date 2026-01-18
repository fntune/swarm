"""Pytest configuration for sdk_live tests.

These tests are excluded from normal pytest runs because they make live API calls.
Run them manually with: python tests/sdk_live/test_xxx.py
"""

import pytest

# Skip all tests in this directory during normal pytest runs
def pytest_ignore_collect(collection_path, config):
    return True
