# Testing Checklist

## Pre-Testing Setup
- [ ] Clone/download the project
- [ ] Navigate to project directory: `/Users/lewis/Desktop/agent`
- [ ] Verify Python 3.8+ is installed: `python3 --version`
- [ ] Install pytest: `pip install pytest`

## Directory Structure Verification
```
/Users/lewis/Desktop/agent/
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_db.py
│   ├── test_scoring.py
│   ├── test_utils.py
│   ├── test_notifications.py
│   └── README.md
├── pytest.ini
├── TEST_SUMMARY.md
└── TESTING_CHECKLIST.md (this file)
```

## Running Tests

### Option 1: Run All Tests
```bash
cd /Users/lewis/Desktop/agent
python3 -m pytest tests/ -v
```

Expected output:
```
tests/test_models.py::TestJobPosting::test_job_posting_creation_with_required_fields PASSED
tests/test_models.py::TestJobPosting::test_job_posting_fingerprint_basic PASSED
... (180+ tests total)
===================== 180+ passed in X.XXs =====================
```

### Option 2: Run Specific Module
```bash
python3 -m pytest tests/test_models.py -v
python3 -m pytest tests/test_db.py -v
python3 -m pytest tests/test_scoring.py -v
python3 -m pytest tests/test_utils.py -v
python3 -m pytest tests/test_notifications.py -v
```

### Option 3: Run with Coverage
```bash
pip install pytest-cov
python3 -m pytest tests/ --cov=. --cov-report=html --cov-report=term-missing
```

### Option 4: Run Specific Test Class
```bash
python3 -m pytest tests/test_models.py::TestJobPosting -v
python3 -m pytest tests/test_db.py::TestUpsertJobs -v
```

### Option 5: Run Specific Test
```bash
python3 -m pytest tests/test_models.py::TestJobPosting::test_job_posting_fingerprint_basic -v
```

## Verification Steps

### 1. Syntax Verification (Already Done)
All test files have been compiled successfully:
- [x] test_models.py - Syntax OK
- [x] test_db.py - Syntax OK
- [x] test_scoring.py - Syntax OK
- [x] test_utils.py - Syntax OK
- [x] test_notifications.py - Syntax OK

### 2. Test Count Verification
Expected test counts:
- test_models.py: 35 tests
- test_db.py: 45+ tests
- test_scoring.py: 50+ tests
- test_utils.py: 40+ tests
- test_notifications.py: 30+ tests
- **Total: 180+ tests**

Run: `python3 -m pytest tests/ --collect-only`

### 3. Fixture Verification
Verify conftest.py fixtures work:
- [x] temp_db_path
- [x] temp_db
- [x] sample_job_posting
- [x] sample_job_postings
- [x] sample_news_item
- [x] sample_news_items
- [x] sample_job_record
- [x] sample_job_records
- [x] mock_config
- [x] mock_environment

### 4. Module Import Verification
Verify all imports work:
```bash
python3 -c "from tests.test_models import *; print('✓ test_models imports OK')"
python3 -c "from tests.test_db import *; print('✓ test_db imports OK')"
python3 -c "from tests.test_scoring import *; print('✓ test_scoring imports OK')"
python3 -c "from tests.test_utils import *; print('✓ test_utils imports OK')"
python3 -c "from tests.test_notifications import *; print('✓ test_notifications imports OK')"
```

## Test Execution Log

### Initial Run
Date: _______________
Command: `python3 -m pytest tests/ -v`
Result: _______________
Passed: ______  Failed: ______  Skipped: ______

### After First Fix (if needed)
Date: _______________
Command: _____________________________
Result: _______________
Passed: ______  Failed: ______  Skipped: ______

### Coverage Report
Date: _______________
Coverage: ______%
Command: `python3 -m pytest tests/ --cov`
Result: _______________

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'pytest'"
**Solution**: Install pytest
```bash
pip install pytest
```

### Issue: "ImportError: No module named 'models'"
**Solution**: Make sure you're running from the project directory
```bash
cd /Users/lewis/Desktop/agent
python3 -m pytest tests/
```

### Issue: "FAILED test_db.py::TestDatabase - sqlite3 database is locked"
**Solution**: This shouldn't happen with the test setup, but if it does:
1. Close any other connections to the test database
2. Run tests with `-n 1` (no parallel execution) if using pytest-xdist

### Issue: "Tests are very slow"
**Solution**: Tests should complete in < 5 seconds total. If slower:
1. Check for actual file I/O (should all be mocked)
2. Check for real network calls (should all be mocked)
3. Review conftest.py fixtures

### Issue: "Some tests fail intermittently"
**Solution**: Tests should be deterministic. If they fail intermittently:
1. Check for time-dependent assertions
2. Verify mocked time functions are working
3. Review fixture isolation

## Code Quality Checks

### Style Check
```bash
pip install flake8
flake8 tests/ --max-line-length=100
```

### Type Checking (Optional)
```bash
pip install mypy
mypy tests/ --ignore-missing-imports
```

### Docstring Coverage
All tests should have docstrings explaining what is being tested.
Run: `python3 -m pytest tests/ --collect-only -q` to verify structure.

## Continuous Integration Integration

### GitHub Actions Example
```yaml
name: Run Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - run: pip install pytest
      - run: pytest tests/ -v
```

### GitLab CI Example
```yaml
test:
  image: python:3.9
  script:
    - pip install pytest
    - pytest tests/ -v
```

## Performance Benchmarking

### Measure Test Runtime
```bash
python3 -m pytest tests/ -v --durations=10
```

Expected timing:
- Most tests: < 50ms
- Database tests: < 100ms
- Total suite: < 5 seconds

## Documentation Review

- [ ] Read tests/README.md
- [ ] Read TEST_SUMMARY.md
- [ ] Review inline test docstrings
- [ ] Review conftest.py fixtures
- [ ] Check pytest.ini configuration

## Final Checklist

- [ ] All test files exist in tests/ directory
- [ ] pytest.ini is in project root
- [ ] All test files have valid Python syntax
- [ ] All fixtures are defined in conftest.py
- [ ] All tests run successfully
- [ ] No external API calls in tests
- [ ] No actual file I/O in tests (except temp SQLite)
- [ ] All mocks are properly cleaned up
- [ ] Test names are descriptive
- [ ] All tests have docstrings
- [ ] Edge cases are covered
- [ ] Error conditions are tested
- [ ] Tests are independent and isolated
- [ ] Tests run in < 5 seconds
- [ ] Coverage is 90%+ for main modules

## Sign-Off

Test Suite Created: ✓ Yes
Tests Validated: _____ 
Date Validated: _____
Validated By: _____

## Additional Resources

- Pytest Documentation: https://docs.pytest.org/
- Testing Best Practices: https://docs.pytest.org/en/stable/goodpractices.html
- Mock Documentation: https://docs.python.org/3/library/unittest.mock.html
- Project Documentation: See tests/README.md and TEST_SUMMARY.md

---
Generated: 2026-03-30
For the Job Scraper Automation Engine (UAE/GCC)
