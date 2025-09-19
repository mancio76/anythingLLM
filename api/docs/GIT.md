# Git Configuration

## .gitignore Files

The project includes comprehensive `.gitignore` files to exclude common system and development files across different operating systems.

### File Structure

```
api/
├── .gitignore           # Root-level exclusions for the entire API project
└── app/.gitignore       # Application-specific exclusions
```

### Coverage

The `.gitignore` files include exclusions for:

#### Operating Systems
- **Windows**: Thumbs.db, Desktop.ini, $RECYCLE.BIN/, *.lnk, etc.
- **macOS**: .DS_Store, .AppleDouble, .Spotlight-V100, .Trashes, etc.
- **Linux**: *~, .fuse_hidden*, .directory, .Trash-*, etc.

#### Development Tools
- **Python**: __pycache__/, *.pyc, .venv/, .pytest_cache/, etc.
- **IDEs**: .idea/, .vscode/, *.sublime-*, .atom/, etc.
- **Editors**: *.swp, *.swo, *~, .emacs.desktop, etc.

#### Application Files
- **Environment**: .env, .env.local, secrets.json, credentials.json
- **Databases**: *.db, *.sqlite, *.sqlite3
- **Logs**: *.log, logs/
- **Temporary**: *.tmp, *.temp, *.bak, *.backup
- **Archives**: *.zip, *.tar, *.gz, *.rar, etc.

#### Testing and Coverage
- **Coverage**: htmlcov/, .coverage, coverage.xml
- **Testing**: .pytest_cache/, .tox/, .nox/
- **Cache**: .cache/, .rpt2_cache/

#### Build and Distribution
- **Python**: build/, dist/, *.egg-info/
- **Node.js**: node_modules/, .npm, .yarn-integrity
- **General**: tmp/, temp/, storage/, uploads/

## Best Practices

### Environment Files
- Never commit `.env` files with real credentials
- Use `.env.example` as a template
- Document required environment variables

### Sensitive Data
- Never commit API keys, passwords, or secrets
- Use environment variables for configuration
- Add sensitive file patterns to .gitignore

### IDE Configuration
- Exclude IDE-specific files (.idea/, .vscode/)
- Share only essential project configuration
- Use .editorconfig for consistent formatting

### Temporary Files
- Exclude all temporary and cache files
- Clean up build artifacts regularly
- Use .gitignore to prevent accidental commits

## Customization

### Adding New Exclusions

To add new file patterns to ignore:

1. **Project-wide exclusions**: Add to `api/.gitignore`
2. **App-specific exclusions**: Add to `api/app/.gitignore`

### Common Patterns

```gitignore
# Custom application files
custom-config.json
local-settings.py

# Development databases
dev.db
test.sqlite

# Custom logs
app-*.log
debug-*.txt

# User-specific files
.user-settings
personal-notes.md
```

### Environment-Specific

```gitignore
# Development only
dev-tools/
local-scripts/

# Production artifacts
production.log
deployment-keys/

# Testing artifacts
test-results/
benchmark-data/
```

## Git Hooks

Consider setting up Git hooks for:

- **Pre-commit**: Run linting and formatting
- **Pre-push**: Run tests
- **Commit-msg**: Validate commit message format

Example pre-commit hook:
```bash
#!/bin/sh
# Run black and isort before commit
black app/ tests/
isort app/ tests/
pytest --maxfail=1
```

## Repository Maintenance

### Regular Cleanup

```bash
# Remove untracked files (be careful!)
git clean -fd

# Remove ignored files
git clean -fX

# Check what would be removed
git clean -fdn
```

### Large Files

For large files, consider:
- Git LFS (Large File Storage)
- External storage solutions
- Proper .gitignore patterns

### Security

- Regularly audit committed files
- Use tools like `git-secrets` or `truffleHog`
- Review .gitignore effectiveness
- Monitor for accidentally committed secrets