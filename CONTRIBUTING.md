# Contributing to MedDraft_AI

Thank you for helping improve `MedDraft_AI`!

## Code Style & Guidelines
- Follow PEP 8 guidelines for Python code.
- Use explicit type hints for function arguments and return values.
- Keep agent prompts modular inside `meddraft_ai/prompts/`.
- Ensure all citation references are verified via CrossRef/PubMed APIs — never allow hallucinated citations.
- When adding a prompt pack under `meddraft_ai/prompts/`, register its folder in `REGISTERED_PROMPT_SUBDIRS` (`meddraft_ai/core/skill_registry.py`) and extend the registration tests in `tests/test_skill_registry.py`.
- When adding an agent skill under `.agents/skills/`, pin it in `skills-lock.json` (`npx skills` lockfile format); `tests/test_skills_lock.py` enforces lock/ directory coverage.

## Running Tests
Run pytest to verify modules:
```bash
pytest tests/ -v
```

On Windows Python 3.12, a known pypdfium2 native crash can occur at collection time (pytest recovers and runs all other tests — see `tests/conftest.py`). To suppress it:
```bash
pytest tests/ -v --ignore=tests/test_pdf.py
```

## Pull Request Process
1. Fork the repository and create your feature branch.
2. Add unit tests for any new features or bug fixes.
3. Verify that all automated tests pass.
4. Submit a detailed Pull Request.
