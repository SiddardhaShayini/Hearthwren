"""Project structure, manifest, and toolchain detector for Hearthwren.

Auto-detects languages, package manifests, test frameworks, linters,
and entry points without modifying any files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_MAP = {
    "pyproject.toml": "Python (PEP 621 / Poetry / Flit)",
    "setup.py": "Python (Setuptools)",
    "requirements.txt": "Python (pip)",
    "Pipfile": "Python (Pipenv)",
    "package.json": "JavaScript / TypeScript (Node.js)",
    "Cargo.toml": "Rust (Cargo)",
    "go.mod": "Go (Go Modules)",
    "Makefile": "Make",
    "CMakeLists.txt": "C / C++ (CMake)",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java / Kotlin (Gradle)",
}


@dataclass
class ProjectSummary:
    """Summary of auto-detected project characteristics."""

    workspace_name: str
    primary_language: str
    languages_detected: list[str] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    test_framework: str | None = None
    linters: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    total_source_files: int = 0
    is_git: bool = False
    is_hwren_init: bool = False


class ProjectDetector:
    """Non-destructive workspace scanner for tech stack detection."""

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()

    def detect(self) -> ProjectSummary:
        """Scan workspace and assemble complete project summary."""
        manifests: list[str] = []
        languages: list[str] = []

        # 1. Detect manifests
        for filename in MANIFEST_MAP:
            target = self.workspace_root / filename
            if target.exists():
                manifests.append(filename)

        # 2. Detect languages based on manifests & extensions
        ext_counts: dict[str, int] = {}
        source_count = 0
        entry_points: list[str] = []

        # Common entry point filenames
        known_entries = {
            "main.py",
            "app.py",
            "cli.py",
            "index.js",
            "index.ts",
            "main.ts",
            "main.rs",
            "lib.rs",
            "main.go",
        }

        ignore_dirs = {".git", ".hearthwren", "node_modules", ".venv", "venv", "__pycache__", "build", "dist"}

        for p in self.workspace_root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in ignore_dirs for part in p.parts):
                continue

            ext = p.suffix.lower()
            if ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".c", ".cpp", ".java"):
                source_count += 1
                ext_counts[ext] = ext_counts.get(ext, 0) + 1

                if p.name.lower() in known_entries:
                    try:
                        rel = str(p.relative_to(self.workspace_root))
                        entry_points.append(rel)
                    except ValueError:
                        pass

        # Language mapping from extensions
        if ext_counts.get(".py", 0) > 0 or "pyproject.toml" in manifests:
            languages.append("Python")
        if any(ext_counts.get(e, 0) > 0 for e in (".js", ".ts", ".jsx", ".tsx")) or "package.json" in manifests:
            languages.append("JavaScript/TypeScript")
        if ext_counts.get(".rs", 0) > 0 or "Cargo.toml" in manifests:
            languages.append("Rust")
        if ext_counts.get(".go", 0) > 0 or "go.mod" in manifests:
            languages.append("Go")
        if ext_counts.get(".c", 0) > 0 or ext_counts.get(".cpp", 0) > 0:
            languages.append("C/C++")

        primary_lang = languages[0] if languages else "Generic / Unknown"

        # 3. Detect test framework
        test_framework: str | None = None
        if "Python" in languages:
            if (self.workspace_root / "pytest.ini").exists() or (self.workspace_root / "tests").is_dir():
                test_framework = "pytest"
            else:
                test_framework = "unittest"
        elif "JavaScript/TypeScript" in languages:
            pkg_json = self.workspace_root / "package.json"
            if pkg_json.exists():
                try:
                    data = json.loads(pkg_json.read_text(encoding="utf-8"))
                    scripts = data.get("scripts", {})
                    if "test" in scripts:
                        test_framework = f"npm test ({scripts['test']})"
                except Exception:
                    test_framework = "npm test"
        elif "Rust" in languages:
            test_framework = "cargo test"
        elif "Go" in languages:
            test_framework = "go test ./..."

        # 4. Detect linters / formatters
        linters: list[str] = []
        if (self.workspace_root / "ruff.toml").exists() or (self.workspace_root / ".ruff.toml").exists():
            linters.append("ruff")
        if (self.workspace_root / ".eslintrc").exists() or (self.workspace_root / ".eslintrc.json").exists():
            linters.append("eslint")
        if (self.workspace_root / ".prettierrc").exists():
            linters.append("prettier")

        # 5. Git & Hearthwren status
        is_git = (self.workspace_root / ".git").is_dir()
        is_hwren = (self.workspace_root / ".hearthwren").is_dir()

        return ProjectSummary(
            workspace_name=self.workspace_root.name,
            primary_language=primary_lang,
            languages_detected=languages,
            manifests=manifests,
            test_framework=test_framework,
            linters=linters,
            entry_points=sorted(entry_points)[:5],
            total_source_files=source_count,
            is_git=is_git,
            is_hwren_init=is_hwren,
        )

    def generate_markdown_summary(self, summary: ProjectSummary | None = None) -> str:
        """Format detection results into a clean markdown block."""
        s = summary or self.detect()
        manifest_str = ", ".join(f"`{m}`" for m in s.manifests) if s.manifests else "None"
        entries_str = ", ".join(f"`{e}`" for e in s.entry_points) if s.entry_points else "Standard layout"
        linters_str = ", ".join(f"`{l}`" for l in s.linters) if s.linters else "Standard"

        return f"""- **Primary Language:** {s.primary_language} ({', '.join(s.languages_detected)})
- **Manifests:** {manifest_str}
- **Test Framework:** `{s.test_framework or 'Not detected'}`
- **Linters/Formatters:** {linters_str}
- **Discovered Entry Points:** {entries_str}
- **Source Files:** {s.total_source_files} tracked files
- **Version Control:** {'Git repository' if s.is_git else 'Not initialized'}
"""
