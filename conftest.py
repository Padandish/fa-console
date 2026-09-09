# -*- coding: utf-8 -*-
"""Pytest configuration for the fa-console test suite.

Root-level ``conftest.py`` puts the project root on ``sys.path`` so the
tests can ``import fa_console`` from a plain source checkout without an
install step.
"""

import pytest


@pytest.fixture(autouse=True)
def builtin_engine(monkeypatch):
    """Force the dependency-free builtin backend for every test.

    The optional ``arabic-reshaper`` + ``python-bidi`` backend produces
    slightly different (equally correct) glyph streams, so the golden
    tests pin the builtin engine to stay deterministic on every machine.
    """
    import fa_console

    monkeypatch.setattr(fa_console._transformer, "_lib_transform", None)
    monkeypatch.setattr(fa_console._transformer, "_lib_checked", True)
