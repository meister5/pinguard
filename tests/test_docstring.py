"""The example in the package docstring is the first thing anyone reads."""

import doctest

import pinguard


def test_module_docstring_examples_still_hold():
    results = doctest.testmod(pinguard, optionflags=doctest.ELLIPSIS, verbose=False)
    assert results.failed == 0, "the README-facing example in pinguard/__init__.py is out of date"
    assert results.attempted > 0
