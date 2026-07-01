# Contributing to DevMind

First off, thank you for taking the time to contribute! Contributions from the community make DevMind better for everyone.

This guide outlines our development workflow and standards.

---

## 🗺️ Git Branching Strategy & Pull Requests

To ensure code stability, we do not commit directly to the `main` branch. 

1.  **Find or Create an Issue**: Before coding, make sure there is an open issue discussing the bug or feature.
2.  **Create a Feature Branch**: Branch off from `main` with a descriptive name:
    *   `git checkout -b feature/your-feature-name`
    *   `git checkout -b fix/bug-description`
3.  **Commit Code**: Write clean commits explaining *what* changed and *why*.
4.  **Open a Pull Request (PR)**:
    *   Push your branch to GitHub.
    *   Create a PR targeting `main` using our Pull Request Template.
    *   Request reviews from maintainers.
    *   Once approved, merge via **Squash and Merge** to keep the Git history clean.

---

## 🛠️ Local Development Setup

To set up your workstation to write code for DevMind:

1.  Clone the repository:
    ```bash
    git clone https://github.com/Anishp-cell/devmind-CLI.git
    cd devmind-CLI
    ```
2.  Create a virtual environment and activate it:
    ```bash
    python -m venv .venv
    # Windows:
    .venv\Scripts\activate
    # macOS/Linux:
    source .venv/bin/activate
    ```
3.  Install dependencies in editable development mode:
    ```bash
    pip install -e .[dev]
    ```
    *(The `[dev]` option installs optional packages like `black`, `isort`, and `pytest` for formatting and testing).*

---

## 🎨 Code Style and Formatting

We use standard Python tools to maintain consistent formatting. Before committing your code, please run:

*   **Formatting (Black)**: `black devmind/`
*   **Imports Sorting (isort)**: `isort devmind/`

---

## 📦 How to Release and Publish a New Version

When merging code that changes features, we increment the version following semantic versioning (`major.minor.patch`).

1.  Open [pyproject.toml](pyproject.toml) and update the `version` field:
    ```toml
    [project]
    name = "devmind-cli"
    version = "0.1.5" # Increment patch, minor, or major
    ```
2.  Delete any old compilation files:
    ```bash
    Remove-Item -Path dist -Recurse -Force -ErrorAction SilentlyContinue
    ```
3.  Build the new wheel:
    ```bash
    python -m build
    ```
4.  Upload to PyPI (requires maintainer credentials):
    ```bash
    twine upload dist/*
    ```
5.  Create a Tag and Release on GitHub matching the version number (e.g. `v0.1.5`).
