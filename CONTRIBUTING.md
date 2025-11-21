# Contributing to Immich Manager

Thank you for considering contributing to Immich Manager! This document provides guidelines for contributing to the project.

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help create a welcoming environment for all

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported
2. Use the issue template
3. Include:
   - Operating system and version
   - Python version
   - Immich version
   - Steps to reproduce
   - Expected vs actual behavior
   - Relevant logs

### Suggesting Features

1. Check if the feature has been suggested
2. Describe the use case
3. Explain why it would be useful
4. Provide examples if possible

### Pull Requests

1. **Fork the repository**

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Follow existing code style
   - Add comments for complex logic
   - Update documentation
   - Add tests if applicable

4. **Test thoroughly**
   ```bash
   # Test Server Manager
   cd server-manager
   source venv/bin/activate
   python -m pytest tests/

   # Test installation scripts
   ./scripts/50-test-installation.sh
   ```

5. **Commit with clear messages**
   ```bash
   git commit -m "Add: feature description"
   git commit -m "Fix: bug description"
   git commit -m "Update: documentation improvement"
   ```

6. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## Development Setup

### Prerequisites

- Ubuntu/Debian Linux
- Python 3.9+
- Immich installed and running
- Docker and Docker Compose

### Local Development

```bash
# Clone your fork
git clone https://github.com/yourusername/immich-manager.git
cd immich-manager

# Server Manager development
cd server-manager
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-cov black flake8

# Run in development mode
python -m src.main

# Photo Curator development
cd ../photo-curator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

## Code Style

### Python

- Follow PEP 8
- Use type hints
- Write docstrings for functions
- Maximum line length: 100 characters

```python
def example_function(param: str) -> Dict[str, Any]:
    """
    Brief description of function.

    Args:
        param: Description of parameter

    Returns:
        Dictionary with results
    """
    pass
```

### Bash Scripts

- Use ShellCheck
- Add error handling (`set -e`)
- Include comments for complex sections
- Use functions for reusable code

```bash
#!/bin/bash
set -e

function my_function() {
    local param="$1"
    # Function logic
}
```

## Testing

### Unit Tests

```bash
cd server-manager
source venv/bin/activate
pytest tests/ -v
```

### Integration Tests

```bash
# Run full installation test
./scripts/50-test-installation.sh
```

### Manual Testing

1. Install on clean system (VM recommended)
2. Test each phase independently
3. Verify web dashboards work
4. Test backup and restore
5. Test remote access
6. Verify security features

## Documentation

- Update README.md for user-facing changes
- Update code comments for technical changes
- Add inline documentation for complex logic
- Update configuration examples if needed

## Release Process

1. Update version numbers
2. Update CHANGELOG.md
3. Test on clean system
4. Create release tag
5. Update documentation

## Questions?

- Open an issue for questions
- Join Immich Discord: https://discord.immich.app
- Check existing issues and PRs

## Recognition

Contributors will be:
- Listed in README.md
- Mentioned in release notes
- Credited in commits

Thank you for contributing! 🎉
