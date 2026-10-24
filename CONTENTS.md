# Repository layout

```
kaggle-mcp/
├── kaggle_mcp.py
├── kaggle-mcp.sh
├── kaggle-mcp.cmd
├── requirements.txt
├── pyproject.toml
├── .env.example
├── LICENSE
├── README.md
├── CHANGELOG.md
├── claude_desktop_config.example.json
└── examples/
    ├── claude_desktop_config.json
    ├── claude_code_settings.json
    ├── codex_config.toml
    ├── cursor_mcp.json
    ├── hermes_config.yaml
    ├── windsurf_mcp_config.json
    ├── opencode_config.json
    ├── continue_config.yaml
    └── vscode_mcp.json
```

## Experiment workflow (3.1)
- `kaggle_experiments.py`: local SQLite provenance and comparisons
- `tests/test_experiments.py`: offline regression tests
- `examples/experiment_demo.py`: runnable synthetic demonstration
- `docs/EXPERIMENTS.md`: usage and limits
- `docs/ROADMAP.md`: implemented features and future milestones
- `.github/workflows/tests.yml`: cross-platform test and wheel-build CI
