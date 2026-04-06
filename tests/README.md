# Unit Tests for Job Scraper Project

Comprehensive test suite for the UAE/GCC job scraper automation engine. These tests cover all exported functions and classes with focus on edge cases, error conditions, and boundary conditions.

## Test Coverage

### test_models.py (35 tests)
Tests for data models in `models.py`:
- **JobPosting dataclass**
  - Field initialization and defaults
  - Fingerprint generation (SHA1 hashing)
  - Case-insensitivity and whitespace normalization
  - Serialization via `to_dict()`
  - Unicode support and special characters

- **NewsItem dataclass**
  - Field initialization and defaults
  - Fingerprint from URL
  - URL normalization and case handling
  - Serialization and unicode support

### test_db.py (45+ tests)
Tests for database operations in `db.py`:
- **Initialization and Schema**
  - Database creation
  - Table schema validation
  - Parent directory creation

- **Upsert Operations**
  - Single and batch job insertion
  - Duplicate detection and handling
  - Timestamp tracking (first_seen_at, last_seen_at)
  - LinkedIn URL normalization
  - News item upsert

- **Query Methods**
  - `fetch_all_jobs()` - retrieval and ordering
  - `fetch_recent_news()` - time-based filtering
  - `jobs_first_seen_since()` - hourly filtering
  - `stats()` - aggregation and statistics
  - `source_total_counts()` - source aggregation
  - `source_new_counts()` - time-windowed counts
  - `source_daily_counts()` - daily aggregation

- **Filtering and Purging**
  - `delete_sources()` - source-based deletion
  - `purge_language_filtered_jobs()` - language filtering
  - `purge_hard_excluded_jobs()` - hard exclusion rules
  - `purge_reject_feedback_jobs()` - user feedback filtering

- **Special Methods**
  - `normalize_linkedin_urls()` - URL normalization
  - `track_player_mentions()` - player tracking
  - `compute_news_topics()` - topic classification

### test_scoring.py (50+ tests)
Tests for job matching and scoring in `scoring.py`:
- **Filtering Functions**
  - `is_language_filtered_out()` - language detection
  - `is_hard_excluded_job()` - hard exclusion rules
  - `is_exec_tech_reject_job()` - executive role rejection

- **Categorization**
  - `auto_category_for_record()` - automatic categorization
  - Category detection (crypto_product, payments, casino, commercial, compliance, recruiter)

- **List Operations**
  - `unique_preserve_order()` - deduplication
  - `filter_records_by_sources()` - source filtering

- **Scoring Engine**
  - `evaluate_fit()` - comprehensive job fitting
  - Location scoring (Dubai, Abu Dhabi, UAE, remote, GCC)
  - Domain tag detection and scoring
  - Role tag matching
  - Resume skill matching
  - Negative tag detection

- **Record Processing**
  - `annotate_records()` - enrichment with scores and tags
  - `focus_records()` - qualifying job filtering
  - `top_recommendations()` - top N recommendations
  - `calculate_match_score()` - score calculation

- **Utilities**
  - `source_label()` - source name mapping

### test_utils.py (40+ tests)
Tests for utility functions in `utils.py`:
- **Time Operations**
  - `utc_now()` - UTC datetime generation
  - `format_seen_timestamp()` - timestamp formatting

- **Text Processing**
  - `clean_text()` - HTML tag removal and normalization
  - `normalize_linkedin_url()` - LinkedIn URL normalization
  - `normalize_linkedin_identifier()` - ID normalization
  - `normalize_phrase()` - phrase normalization

- **File Operations**
  - `load_reject_feedback()` - JSON loading with error handling
  - `load_telegram_sent_history()` - history loading
  - `save_telegram_sent_history()` - history persistence
  - `save_scrape_state()` - state tracking

### test_notifications.py (30+ tests)
Tests for notification functions in `notifications.py`:
- **Aggregation**
  - `source_total_counts()` - total counts by source
  - `source_daily_counts()` - daily counts aggregation

- **Telegram Notifications**
  - `send_telegram_text()` - message sending
  - Authentication handling
  - URL encoding and message formatting
  - Error handling (network failures)

- **Selective Broadcasting**
  - `maybe_send_telegram()` - conditional sending
  - Duplicate detection and filtering
  - Message composition with top jobs
  - Multiple notification scenarios

## Test Fixtures (conftest.py)

Shared fixtures for test configuration:
- `temp_db_path` - Temporary database file
- `temp_db` - Database instance
- `sample_job_posting` - Single JobPosting
- `sample_job_postings` - Multiple JobPostings
- `sample_news_item` - Single NewsItem
- `sample_news_items` - Multiple NewsItems
- `sample_job_record` - Job record dictionary
- `sample_job_records` - Multiple job records
- `mock_config` - Configuration dictionary
- `mock_environment` - Environment variables

## Running Tests

### Prerequisites
```bash
pip install pytest pytest-cov
```

### Run All Tests
```bash
pytest tests/
```

### Run With Verbose Output
```bash
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/test_models.py
```

### Run Specific Test Class
```bash
pytest tests/test_models.py::TestJobPosting
```

### Run Specific Test
```bash
pytest tests/test_models.py::TestJobPosting::test_job_posting_fingerprint_basic
```

### Run Tests Matching Pattern
```bash
pytest tests/ -k "fingerprint"
```

### Run With Coverage Report
```bash
pytest tests/ --cov=. --cov-report=html --cov-report=term-missing
```

### Run Only Database Tests
```bash
pytest tests/ -m db
```

### Run Only Mock Tests
```bash
pytest tests/ -m mock
```

## Test Organization

Each test file follows a consistent structure:
1. **Imports** - All required modules and test utilities
2. **Test Classes** - Grouped by functionality (e.g., TestJobPosting, TestDatabase)
3. **Test Methods** - Individual test cases with descriptive names
4. **Fixtures** - Setup and teardown using pytest fixtures

### Naming Conventions
- Test files: `test_*.py`
- Test classes: `Test*`
- Test methods: `test_*`
- Fixture names: Descriptive, e.g., `temp_db`, `sample_job_posting`

### Test Method Naming
Format: `test_<function>_<scenario>`

Examples:
- `test_job_posting_fingerprint_basic`
- `test_database_upsert_new_jobs`
- `test_evaluate_fit_good_match`
- `test_send_telegram_text_with_html`

## Test Scenarios Covered

### Normal Operation (Happy Path)
- Basic functionality with typical inputs
- Valid data serialization
- Standard aggregation and filtering
- Expected success conditions

### Edge Cases
- Empty inputs (empty strings, empty lists)
- Single-element collections
- Maximum-length strings
- Unicode and special characters
- Whitespace variations
- Case sensitivity variations

### Error Conditions
- Missing required fields
- Invalid input types
- Out-of-range values
- Network failures
- File I/O errors
- JSON parsing errors

### Boundary Conditions
- Zero/negative numbers
- Empty vs whitespace-only strings
- Time boundaries (past/future)
- First/last elements in collections
- Duplicate entries

## Mocking Strategy

All external dependencies are mocked to ensure test isolation:

### Database
- Uses temporary SQLite databases
- No shared state between tests
- Automatic cleanup via fixtures

### HTTP Requests
- `urllib.request.urlopen` mocked
- `send_telegram_text` uses environment variable mocks
- Network errors tested via exception injection

### File I/O
- File paths mocked with `patch`
- JSON operations mocked
- No actual files created in tests

### Environment Variables
- Mocked using `patch.dict`
- Telegram credentials tested in isolation
- Configuration values parametrized

### Time Functions
- `utc_now()` returns consistent datetime
- No real-time dependencies
- Timestamps are relative and reproducible

## Test Independence

Each test is designed to run independently:
- No shared database state
- No interdependencies
- Tests can run in any order
- Tests can run in parallel

Setup via:
- `setUp`/`tearDown` methods
- `@pytest.fixture` decorators
- `conftest.py` shared fixtures
- Temporary files and databases

## Code Quality

Tests follow Python best practices:
- PEP 8 compliant
- Descriptive test names
- Arrange-Act-Assert pattern
- Clear assertions with meaningful messages
- Proper exception handling
- Comprehensive docstrings

## Continuous Integration

These tests are suitable for CI/CD pipelines:
- All tests are deterministic
- No external service dependencies
- Fast execution (< 5 seconds total)
- Clear pass/fail status
- Detailed error reporting

Example GitHub Actions workflow:
```yaml
- name: Run unit tests
  run: |
    pip install pytest
    pytest tests/ -v --tb=short
```

## Known Limitations

1. **LinkedIn API** - Not tested in integration (requires authentication)
2. **Playwright** - Browser automation not fully tested (requires npm install)
3. **External APIs** - All mocked, not integration tested
4. **Database Migrations** - Schema changes not tested

## Future Improvements

1. Add performance benchmarks
2. Add property-based testing (hypothesis)
3. Add stress tests for large datasets
4. Add integration tests with real services
5. Add mutation testing for coverage gaps

## Contributing

When adding new code:
1. Write tests first (TDD)
2. Ensure 100% function coverage
3. Test all edge cases and error conditions
4. Update this README with new test scenarios
5. Run full test suite before committing

## Support

For test-related issues:
1. Check test output for specific failures
2. Review test documentation in code comments
3. Examine similar tests for patterns
4. Consult pytest documentation
