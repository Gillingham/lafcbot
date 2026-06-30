# Claude Code Guidelines for lafcbot

This document provides guidance for Claude Code when working on the lafcbot project.

## Project Overview

lafcbot is a Discord bot for soccer match information and utilities, powered by FotMob data. The project uses:
- Python 3.13+
- `uv` for dependency management
- py-cord for Discord integration
- pytest for testing

## Development Commands

### Always use `uv` wrappers

**IMPORTANT:** This project uses `uv` for all Python tooling. Always prefix commands with `uv run` or `uv tool run`.

#### Running Python commands
```bash
# ✅ Correct
uv run python run.py
uv run python -m pytest tests/
uv run python -m pytest tests/test_visual_verification.py -v

# ❌ Wrong - don't call python directly
python run.py
python -m pytest tests/
```

#### Running linters and formatters
```bash
# ✅ Correct
uv tool run ruff check .
uv tool run ruff format .
uv tool run mypy lafcbot/

# ❌ Wrong - don't call tools directly
ruff check .
mypy lafcbot/
```

### Pre-commit hooks

The project uses [pre-commit](https://pre-commit.com/) to automatically run linting and formatting before each commit.

**Setup (one-time):**
```bash
uv tool install pre-commit
pre-commit install
```

**What it does:**
- Runs `ruff --fix` to auto-fix linting issues
- Runs `ruff-format` to format code
- Prevents commits if unfixable issues remain

**If pre-commit blocks your commit:**
- Review the changes it made (they're auto-staged)
- If issues can't be auto-fixed, fix them manually
- Commit again

**To bypass (not recommended):**
```bash
git commit --no-verify  # Skip pre-commit hooks
```

#### Installing dependencies
```bash
# ✅ Correct
uv sync                    # Install/update all dependencies
uv add package-name        # Add a new dependency
uv add --dev package-name  # Add a dev dependency

# ❌ Wrong
pip install package-name
```

## Testing

### Running tests
```bash
# Run all tests (excluding integration tests)
uv run python -m pytest tests/ -v -m "not integration"

# Run only integration tests (calls real FotMob API)
uv run python -m pytest tests/test_integration/ -v -m integration

# Run all tests including integration
uv run python -m pytest tests/ -v

# Run specific test file
uv run python -m pytest tests/test_visual_verification.py -v

# Run tests with coverage report
uv run python -m pytest tests/ -m "not integration" --cov=lafcbot --cov-report=term-missing --cov-report=html

# View HTML coverage report (after running coverage)
open htmlcov/index.html
```

### Test types
- **Unit tests** - Fast tests with mocked dependencies
- **Integration tests** - Tests that call real FotMob API (marked with `@pytest.mark.integration`)
  - Use these to verify our code works with actual API responses
  - Will catch breaking changes to FotMob's API structure
  - Slower but more reliable for catching real-world issues

### Code coverage
The project uses pytest-cov for code coverage tracking. Coverage configuration is in `pyproject.toml`.

**Current coverage:**
- Unit tests only: 25.52%
- All tests (with integration): **28.72%**

**High coverage areas:**
- `lafcbot/formatters/world_cup.py` - 85% (well-tested formatting logic)
- `lafcbot/clients/fotmob/models.py` - 100% (data models)
- `lafcbot/clients/fotmob/parser.py` - 78% (thanks to integration tests!)
- `lafcbot/utils/countries.py` - 68% (country utilities)
- `lafcbot/clients/fotmob/client.py` - 47% (integration tests cover API paths)

**Low coverage areas (need more tests):**
- Discord cogs (0-8%) - bot commands, not easily unit-testable
- `lafcbot/clients/fotmob/client.py` - 28% (complex API client)
- `lafcbot/tasks/world_cup.py` - 37% (background tasks)

**Coverage gaps are expected for:**
- Discord bot setup and command handling (integration-test territory)
- Database operations (require DB setup)
- Background tasks (require async runtime setup)

Focus testing efforts on:
1. Formatters (user-facing output)
2. Event detection logic (critical for live monitoring)
3. FotMob API parsing (catches API changes)

### Visual verification tests
The project includes visual verification tests in `tests/test_visual_verification.py` that output formatted match notifications for human review. See `tests/VISUAL_VERIFICATION.md` for details.

## Code Style and Conventions

### File structure
- `lafcbot/` - Main package code
  - `commands/` - Discord bot commands
  - `formatters/` - Message formatting logic
  - `match_events/` - Live match monitoring and notifications
  - `utils/` - Utility functions
- `tests/` - Test files
  - Test files should mirror the structure of the main package
  - Use descriptive test names that explain what is being tested

### Testing approach
- Use mocks from `lafcbot/testing/discord_mocks.py` for Discord objects
- Use fixtures for common test data
- Write visual verification tests for user-facing message formatting

### Comments and documentation
- Default to writing no comments
- Only add comments when the WHY is non-obvious
- Don't explain WHAT the code does (well-named identifiers do that)
- Use docstrings for public functions with complex parameters

### Error handling
- Only validate at system boundaries (user input, external APIs)
- Trust internal code and framework guarantees
- Don't add error handling for scenarios that can't happen

## Project-specific patterns

### Discord notifications
- Goal notifications use `notify_goal()` in `lafcbot/match_events/notifiers.py`
- Keep notifications concise - avoid unnecessary blank lines
- Use country flags where available via `lafcbot/utils/countries.py`

### Time handling
- All times should be displayed in the configured timezone (default: Pacific)
- Use `astimezone(self.timezone)` for conversion
- Format times consistently: `%b %d, %I:%M %p PT`

### FotMob API integration
- Match details fetched via `fotmob_client.get_match_details()`
- Handle API errors gracefully with fallbacks
- Cache results appropriately to avoid rate limiting

## Common tasks

### Adding a new command
1. Create the command in `lafcbot/commands/`
2. Add tests in `tests/test_commands/`
3. Update README.md if it's a user-facing feature

### Modifying notification format
1. Update the formatter in `lafcbot/formatters/` or notifier in `lafcbot/match_events/notifiers.py`
2. Add/update visual verification test in `tests/test_visual_verification.py`
3. Run tests: `uv run python -m pytest tests/test_visual_verification.py -v`
4. Review the visual output to ensure it looks correct

### Debugging live match monitoring
1. Check logs for event detection issues
2. Use visual verification tests to confirm formatting
3. Test with actual match data if possible
