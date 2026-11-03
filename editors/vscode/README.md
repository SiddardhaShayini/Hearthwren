# Hearthwren VS Code Extension

A lightweight, zero-dependency VS Code extension wrapper around the **Hearthwren** (`hwren`) CLI.

Designed specifically for **CPU-only laptops with 8 GB RAM**.

## Features

- **Status Bar Health Monitor:** Shows current Hearthwren status and RAM ceiling in the VS Code status bar.
- **Interactive Planning (`Hearthwren: Plan a Task`):** Prompts for a task description, invokes `hwren plan`, and streams an ordered implementation plan to the Hearthwren output channel without modifying any code.
- **Architectural Guidance (`Hearthwren: Ask for Guidance`):** Explains project structure, test patterns, or toolchain steps.
- **Project Verification (`Hearthwren: Verify Project Tests`):** Discovers and runs tests via `hwren verify`, capturing real exit codes and failure lines.
- **Unified Diff (`Hearthwren: View Staged/Workspace Diff`):** Previews changes before staging or committing.
- **Task Resumption (`Hearthwren: Resume Last Task`):** Restores task context from `.hearthwren/session.json`.

## Requirements

1. Python 3.11+ installed.
2. Hearthwren installed (`pip install -e .` or `pip install hearthwren`).

## Installation

Open this folder in VS Code, or package with `vsce package` and install the `.vsix` file.
