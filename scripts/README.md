# Utility Scripts

This directory contains utility and verification scripts for the FUT Market project.

## Scripts

### verify_priority_system.py
Manual verification script for the priority system. Use this to:
- Test hotness calculator with sample data
- Verify tier assignments
- Check priority queue configuration
- Display tier distribution

**Usage:**
```bash
uv run python scripts/verify_priority_system.py
```

**When to use:**
- After deploying priority system changes
- To verify tier calculations are working
- For debugging tier assignment issues

## Running Tests

Unit tests are located in `players/tests/`. Run them using Django's test runner:

```bash
# Run all tests
uv run python manage.py test players.tests

# Run specific test class
uv run python manage.py test players.tests.test_hotness_calculator.TestCardHotnessCalculator

# Run specific test method
uv run python manage.py test players.tests.test_hotness_calculator.TestCardHotnessCalculator.test_get_tier_from_score
```