# Test Suite Index

## Quick Navigation

### Test Files

1. **tests/test_models.py** - Data Models
   - 35+ tests
   - JobPosting dataclass tests
   - NewsItem dataclass tests
   - Path: `/Users/lewis/Desktop/agent/tests/test_models.py`

2. **tests/test_db.py** - Database Operations
   - 45+ tests
   - Database initialization and schema
   - Job/news upsert operations
   - Query methods (fetch, stats, counts)
   - Filtering and purging operations
   - Path: `/Users/lewis/Desktop/agent/tests/test_db.py`

3. **tests/test_scoring.py** - Job Matching and Scoring
   - 50+ tests
   - Language filtering
   - Job exclusion rules
   - Automatic categorization
   - Match score evaluation
   - Record annotation and recommendations
   - Path: `/Users/lewis/Desktop/agent/tests/test_scoring.py`

4. **tests/test_utils.py** - Utility Functions
   - 40+ tests
   - DateTime handling
   - Text processing and cleaning
   - URL normalization
   - File operations (reject feedback, history)
   - Path: `/Users/lewis/Desktop/agent/tests/test_utils.py`

5. **tests/test_notifications.py** - Notification Functions
   - 30+ tests
   - Source count aggregation
   - Telegram message sending
   - Job broadcast filtering
   - Path: `/Users/lewis/Desktop/agent/tests/test_notifications.py`

### Configuration Files

1. **pytest.ini** - Pytest Configuration
   - Test discovery patterns
   - Output formatting
   - Test markers
   - Path: `/Users/lewis/Desktop/agent/pytest.ini`

2. **tests/conftest.py** - Shared Fixtures
   - Temporary database fixtures
   - Sample data generators
   - Mock utilities
   - Path: `/Users/lewis/Desktop/agent/tests/conftest.py`

3. **tests/__init__.py** - Package Documentation
   - Test structure overview
   - Running instructions
   - Path: `/Users/lewis/Desktop/agent/tests/__init__.py`

### Documentation

1. **tests/README.md** - Complete Test Guide
   - Test coverage breakdown
   - Running instructions
   - Test organization and naming
   - Mocking strategy
   - Contributing guidelines

2. **TEST_SUMMARY.md** - Project Summary
   - Deliverables overview
   - Coverage analysis
   - Testing methodology
   - Quality metrics

3. **TESTING_CHECKLIST.md** - Verification Checklist
   - Setup instructions
   - Running tests
   - Verification steps
   - Troubleshooting guide

4. **TESTS_INDEX.md** - This File
   - Quick navigation
   - File organization

## File Statistics

```
Total Test Files: 5
Total Test Lines: 2,682
Total Tests: 180+

Breakdown:
- test_models.py:      464 lines,  35 tests
- test_db.py:          718 lines,  45+ tests
- test_scoring.py:     638 lines,  50+ tests
- test_utils.py:       471 lines,  40+ tests
- test_notifications.py: 451 lines, 30+ tests
- conftest.py:         273 lines, 10 fixtures
- __init__.py:         34 lines
```

## Key Locations

| Item | Path |
|------|------|
| Test Directory | `/Users/lewis/Desktop/agent/tests/` |
| Pytest Config | `/Users/lewis/Desktop/agent/pytest.ini` |
| Models Tests | `/Users/lewis/Desktop/agent/tests/test_models.py` |
| Database Tests | `/Users/lewis/Desktop/agent/tests/test_db.py` |
| Scoring Tests | `/Users/lewis/Desktop/agent/tests/test_scoring.py` |
| Utils Tests | `/Users/lewis/Desktop/agent/tests/test_utils.py` |
| Notifications Tests | `/Users/lewis/Desktop/agent/tests/test_notifications.py` |
| Fixtures Config | `/Users/lewis/Desktop/agent/tests/conftest.py` |
| Test Guide | `/Users/lewis/Desktop/agent/tests/README.md` |
| Summary | `/Users/lewis/Desktop/agent/TEST_SUMMARY.md` |
| Checklist | `/Users/lewis/Desktop/agent/TESTING_CHECKLIST.md` |

## Running Tests

### All Tests
```bash
cd /Users/lewis/Desktop/agent
python3 -m pytest tests/ -v
```

### By Module
```bash
python3 -m pytest tests/test_models.py -v
python3 -m pytest tests/test_db.py -v
python3 -m pytest tests/test_scoring.py -v
python3 -m pytest tests/test_utils.py -v
python3 -m pytest tests/test_notifications.py -v
```

### Specific Test
```bash
python3 -m pytest tests/test_models.py::TestJobPosting::test_job_posting_fingerprint_basic -v
```

### With Coverage
```bash
python3 -m pytest tests/ --cov=. --cov-report=html
```

## Test Organization

### By Module Tested

#### Models (test_models.py)
- JobPosting initialization
- JobPosting fingerprint generation
- JobPosting serialization
- NewsItem initialization
- NewsItem fingerprint generation
- NewsItem serialization

#### Database (test_db.py)
- Initialization & Schema
- Upsert Operations
- Query Methods
- Filtering & Purging
- Special Methods

#### Scoring (test_scoring.py)
- Language Filtering
- Hard Exclusion Rules
- Automatic Categorization
- Fit Evaluation
- Score Calculation
- Record Processing

#### Utils (test_utils.py)
- Time Operations
- Text Processing
- URL Normalization
- File Operations
- Phrase Normalization

#### Notifications (test_notifications.py)
- Source Aggregation
- Telegram Sending
- Selective Broadcasting

## Test Scenarios

Each test covers:
- ✓ Normal operation (happy path)
- ✓ Edge cases (empty, special chars, unicode)
- ✓ Error conditions (missing fields, invalid types)
- ✓ Boundary conditions (zero, negative, limits)
- ✓ Mocking of external dependencies
- ✓ Isolation and independence

## Quick Reference

### Running First Time
1. Install pytest: `pip install pytest`
2. Run tests: `python3 -m pytest tests/ -v`
3. Review results

### Adding New Tests
1. Edit appropriate test_*.py file
2. Follow naming convention: `test_<function>_<scenario>`
3. Use existing fixtures from conftest.py
4. Add docstring explaining test
5. Run: `pytest tests/test_file.py -v`

### Debugging a Test
```bash
python3 -m pytest tests/test_file.py::TestClass::test_method -vvs
```

### Test Discovery
```bash
python3 -m pytest tests/ --collect-only
```

### Performance Analysis
```bash
python3 -m pytest tests/ -v --durations=10
```

## Documentation Hierarchy

1. **Quick Start** → `TESTING_CHECKLIST.md`
2. **Test Guide** → `tests/README.md`
3. **Project Summary** → `TEST_SUMMARY.md`
4. **Navigation** → `TESTS_INDEX.md` (this file)
5. **Code Reference** → Inline docstrings in test files

## Integration with CI/CD

Tests are ready for:
- GitHub Actions
- GitLab CI
- Jenkins
- Travis CI
- Any Python CI/CD system

See `TESTING_CHECKLIST.md` for CI/CD examples.

## Support Resources

- Pytest Docs: https://docs.pytest.org/
- Testing Best Practices: https://docs.pytest.org/en/stable/goodpractices.html
- Python unittest.mock: https://docs.python.org/3/library/unittest.mock.html
- Project README: See tests/README.md

---

**Total Tests Generated: 180+**
**Total Files: 11 (5 test files + 6 config/docs)**
**Status: Ready to Use**
**Last Generated: 2026-03-30**
