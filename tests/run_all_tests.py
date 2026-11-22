"""
NepFakeV2 test runner (kept for old habits).

The tests are now real pytest tests. This file just calls pytest, so
`python tests/run_all_tests.py` and `pytest` do the same thing.
Extra arguments are passed through, e.g.:
    python tests/run_all_tests.py -k label_mapper
"""
import sys

import pytest

if __name__ == "__main__":
    sys.exit(pytest.main(sys.argv[1:]))
