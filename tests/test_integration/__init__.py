"""Integration tests that call real external APIs.

These tests verify our code works with actual API responses.
They are marked with @pytest.mark.integration and can be run separately.

To run only integration tests:
    uv run python -m pytest tests/test_integration/ -v -m integration

To skip integration tests:
    uv run python -m pytest tests/ -v -m "not integration"
"""
