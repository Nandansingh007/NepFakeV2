"""
NepFakeV2 Test Runner
Run all tests: python tests/run_all_tests.py
"""
import subprocess
import sys
import os

tests = [
    "tests/test_label_mapper.py",
    "tests/test_scrapers.py",
    "tests/test_raw_data.py",
    "tests/test_normalizer.py",
    "tests/test_deduplicator.py",
    "tests/test_pipeline.py",
    "tests/test_dataset.py",
    "tests/test_security.py",
]

print("=" * 60)
print("NepFakeV2 - Full Test Suite")
print("=" * 60)
print()

passed = 0
failed = 0
errors = []

for test in tests:
    if not os.path.exists(test):
        print(f"SKIP: {test} (not found)")
        continue

    result = subprocess.run(
        [sys.executable, test],
        capture_output=True,
    )

    stdout = result.stdout.decode('utf-8', errors='replace').strip()
    stderr = result.stderr.decode('utf-8', errors='replace').strip()

    if result.returncode == 0:
        passed += 1
        print(f"PASS: {test}")
        if stdout:
            print(f"      {stdout}")
    else:
        failed += 1
        errors.append((test, stdout, stderr))
        print(f"FAIL: {test}")

print()
print("=" * 60)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 60)

if errors:
    print()
    print("FAILURES:")
    for test, stdout, stderr in errors:
        print(f"\n--- {test} ---")
        if stdout:
            print(stdout[-1000:])
        if stderr:
            print(stderr[-500:])
    sys.exit(1)
else:
    print()
    print("All tests passed")