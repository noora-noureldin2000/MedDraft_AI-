# Contributing to MedDraft_AI

Thank you for helping improve `MedDraft_AI`!

## Code Style & Guidelines
- Follow PEP 8 guidelines for Python code.
- Use explicit type hints for function arguments and return values.
- Keep agent prompts modular inside `meddraft_ai/prompts/`.
- Ensure all citation references are verified via CrossRef/PubMed APIs — never allow hallucinated citations.

## Running Tests
Run pytest to verify modules:
```bash
pytest tests/ -v
```

## Pull Request Process
1. Fork the repository and create your feature branch.
2. Add unit tests for any new features or bug fixes.
3. Verify that all automated tests pass.
4. Submit a detailed Pull Request.
