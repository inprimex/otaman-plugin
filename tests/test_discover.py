"""Tests for discover-repos.py — repo scanning and draft generation.

Covers:
- Git repo detection
- Non-git project detection (pyproject.toml, .claude/, src/, etc.)
- Tech stack detection (Node.js, Python, ML, Terraform, etc.)
- Owner suggestion heuristics
- OpenSpec detection
- API contracts detection
- Monorepo indicators
- Draft platform.yaml generation and validation
"""

from __future__ import annotations

# Add scripts/ to path so we can import discover-repos
# discover_repos + validate_platform now resolved as package modules
# (otaman_plugin via package; otaman_core via pyproject pythonpath / dep)
# Import with hyphen workaround
import importlib
from pathlib import Path

import pytest

discover = importlib.import_module("otaman_plugin.discover_repos")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a base project directory."""
    return tmp_path


def make_git_repo(path: Path) -> Path:
    """Create a directory with .git/ inside."""
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir()
    return path


def make_non_git_project(path: Path, indicator: str = "pyproject.toml") -> Path:
    """Create a directory that looks like a project but has no .git/."""
    path.mkdir(parents=True, exist_ok=True)
    (path / indicator).write_text("", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _looks_like_project
# ---------------------------------------------------------------------------


class TestLooksLikeProject:
    def test_empty_dir_is_not_project(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        assert discover._looks_like_project(d) is False

    def test_pyproject_toml(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / "pyproject.toml").write_text("[project]", encoding="utf-8")
        assert discover._looks_like_project(d) is True

    def test_requirements_txt(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / "requirements.txt").write_text("flask", encoding="utf-8")
        assert discover._looks_like_project(d) is True

    def test_package_json(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / "package.json").write_text("{}", encoding="utf-8")
        assert discover._looks_like_project(d) is True

    def test_dockerfile(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / "Dockerfile").write_text("FROM python:3.12", encoding="utf-8")
        assert discover._looks_like_project(d) is True

    def test_gitignore(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".gitignore").write_text("*.pyc", encoding="utf-8")
        assert discover._looks_like_project(d) is True

    def test_claude_config_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".claude").mkdir()
        assert discover._looks_like_project(d) is True

    def test_src_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / "src").mkdir()
        assert discover._looks_like_project(d) is True

    def test_readme_with_subdirs(self, tmp_path: Path) -> None:
        """A README.md + multiple subdirs (like watchtower-specs)."""
        d = tmp_path / "specs"
        d.mkdir()
        (d / "README.md").write_text("# Specs", encoding="utf-8")
        (d / "api").mkdir()
        (d / "models").mkdir()
        assert discover._looks_like_project(d) is True

    def test_readme_alone_not_enough(self, tmp_path: Path) -> None:
        """Just a README.md with no subdirs is not a project."""
        d = tmp_path / "notes"
        d.mkdir()
        (d / "README.md").write_text("# Notes", encoding="utf-8")
        assert discover._looks_like_project(d) is False

    def test_go_mod(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / "go.mod").write_text("module example.com/foo", encoding="utf-8")
        assert discover._looks_like_project(d) is True

    def test_cargo_toml(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / "Cargo.toml").write_text("[package]", encoding="utf-8")
        assert discover._looks_like_project(d) is True


# ---------------------------------------------------------------------------
# scan_directory — git vs non-git detection
# ---------------------------------------------------------------------------


class TestScanDirectory:
    def test_git_repos_detected(self, project_dir: Path) -> None:
        make_git_repo(project_dir / "repo-api")
        (project_dir / "repo-api" / "package.json").write_text(
            '{"dependencies":{"express":"^4.0"}}', encoding="utf-8"
        )
        report = discover.scan_directory(project_dir)
        assert len(report["repos"]) == 1
        assert report["repos"][0]["has_git"] is True

    def test_non_git_projects_detected(self, project_dir: Path) -> None:
        """Directories without .git/ but with project indicators are detected."""
        d = project_dir / "my-service"
        d.mkdir()
        (d / "pyproject.toml").write_text("[project]", encoding="utf-8")
        (d / "requirements.txt").write_text("fastapi\nuvicorn", encoding="utf-8")

        report = discover.scan_directory(project_dir)
        assert len(report["repos"]) == 1
        assert report["repos"][0]["name"] == "my-service"
        assert report["repos"][0]["has_git"] is False

    def test_non_git_generates_warning(self, project_dir: Path) -> None:
        make_non_git_project(project_dir / "svc-no-git")
        report = discover.scan_directory(project_dir)
        warnings = [w for w in report["warnings"] if "no .git/" in w]
        assert len(warnings) == 1
        assert "svc-no-git" in warnings[0]

    def test_mixed_git_and_non_git(self, project_dir: Path) -> None:
        """Both git repos and non-git projects are detected together."""
        make_git_repo(project_dir / "api-server")
        (project_dir / "api-server" / "package.json").write_text("{}", encoding="utf-8")

        make_non_git_project(project_dir / "ml-pipeline", "requirements.txt")

        report = discover.scan_directory(project_dir)
        assert len(report["repos"]) == 2
        names = {r["name"] for r in report["repos"]}
        assert "api-server" in names
        assert "ml-pipeline" in names

        git_repo = next(r for r in report["repos"] if r["name"] == "api-server")
        no_git_repo = next(r for r in report["repos"] if r["name"] == "ml-pipeline")
        assert git_repo["has_git"] is True
        assert no_git_repo["has_git"] is False

    def test_empty_dir_not_detected(self, project_dir: Path) -> None:
        """Empty directories are not detected as projects."""
        (project_dir / "empty-dir").mkdir()
        make_git_repo(project_dir / "real-repo")  # need at least one to avoid early return
        (project_dir / "real-repo" / "package.json").write_text("{}", encoding="utf-8")

        report = discover.scan_directory(project_dir)
        names = {r["name"] for r in report["repos"]}
        assert "empty-dir" not in names

    def test_dot_dirs_skipped(self, project_dir: Path) -> None:
        """Hidden directories (starting with .) are skipped."""
        make_git_repo(project_dir / ".hidden-repo")
        make_git_repo(project_dir / "visible-repo")
        (project_dir / "visible-repo" / "package.json").write_text("{}", encoding="utf-8")

        report = discover.scan_directory(project_dir)
        names = {r["name"] for r in report["repos"]}
        assert ".hidden-repo" not in names

    def test_watchtower_like_layout(self, project_dir: Path) -> None:
        """Simulate the watchtower project layout with mixed git/non-git."""
        # Git repos
        make_git_repo(project_dir / "detectmod")
        (project_dir / "detectmod" / "requirements.txt").write_text(
            "torch\nnumpy", encoding="utf-8"
        )
        (project_dir / "detectmod" / "CLAUDE.md").write_text("# Detectmod", encoding="utf-8")

        make_git_repo(project_dir / "pfobos")
        (project_dir / "pfobos" / "pyproject.toml").write_text("[project]", encoding="utf-8")
        (project_dir / "pfobos" / "CLAUDE.md").write_text("# Pfobos", encoding="utf-8")

        make_git_repo(project_dir / "watchtower-sdr-probe")
        (project_dir / "watchtower-sdr-probe" / "requirements.txt").write_text(
            "pandas\nscikit-learn", encoding="utf-8"
        )
        (project_dir / "watchtower-sdr-probe" / "Dockerfile").write_text(
            "FROM python:3.12", encoding="utf-8"
        )

        # Non-git projects
        edge = project_dir / "watchtower-edge"
        edge.mkdir()
        (edge / ".claude").mkdir()
        (edge / "pyproject.toml").write_text("[project]", encoding="utf-8")
        (edge / "src").mkdir()
        (edge / "CLAUDE-edge.md").write_text("# Edge", encoding="utf-8")

        specs = project_dir / "watchtower-specs"
        specs.mkdir()
        (specs / "README.md").write_text("# Specs", encoding="utf-8")
        (specs / "api").mkdir()
        (specs / "api" / "README.md").write_text("# API Specs", encoding="utf-8")
        (specs / "edge").mkdir()
        (specs / "edge" / "README.md").write_text("# Edge Specs", encoding="utf-8")
        (specs / "fusion").mkdir()
        (specs / "fusion" / "README.md").write_text("# Fusion Specs", encoding="utf-8")

        synthetic = project_dir / "watchtower-synthetic"
        synthetic.mkdir()
        (synthetic / "Dockerfile").write_text("FROM python:3.12", encoding="utf-8")
        (synthetic / "docker-compose.yml").write_text("version: '3'", encoding="utf-8")
        (synthetic / "requirements.txt").write_text("torch\nnumpy", encoding="utf-8")
        (synthetic / "CLAUDE-synthetic.md").write_text("# Synthetic", encoding="utf-8")
        (synthetic / "core").mkdir()

        report = discover.scan_directory(project_dir)

        # All 6 should be detected
        assert len(report["repos"]) == 6

        names = {r["name"] for r in report["repos"]}
        assert names == {
            "detectmod",
            "pfobos",
            "watchtower-sdr-probe",
            "watchtower-edge",
            "watchtower-specs",
            "watchtower-synthetic",
        }

        # Check git vs non-git
        for r in report["repos"]:
            if r["name"] in ("detectmod", "pfobos", "watchtower-sdr-probe"):
                assert r["has_git"] is True, f"{r['name']} should have git"
            else:
                assert r["has_git"] is False, f"{r['name']} should not have git"

        # Non-git projects generate warnings
        no_git_warnings = [w for w in report["warnings"] if "no .git/" in w]
        assert len(no_git_warnings) == 3

        # watchtower-edge should have CLAUDE.md detected (CLAUDE-edge.md variant)
        edge_repo = next(r for r in report["repos"] if r["name"] == "watchtower-edge")
        assert edge_repo["has_claude_md"] is True
        assert edge_repo["has_claude_config"] is True  # .claude/ dir

        # watchtower-specs should be detected as docs
        specs_repo = next(r for r in report["repos"] if r["name"] == "watchtower-specs")
        assert "docs" in specs_repo["tech"]


# ---------------------------------------------------------------------------
# Tech stack detection
# ---------------------------------------------------------------------------


class TestTechStack:
    def test_python_ml(self, tmp_path: Path) -> None:
        d = tmp_path / "ml"
        d.mkdir()
        (d / "requirements.txt").write_text("torch\nnumpy\npandas", encoding="utf-8")
        tech, owner = discover.detect_tech_stack(d)
        assert "python" in tech
        assert "python-ml" in tech
        assert owner == "data-agent"

    def test_python_web(self, tmp_path: Path) -> None:
        d = tmp_path / "api"
        d.mkdir()
        (d / "requirements.txt").write_text("fastapi\nuvicorn\nsqlalchemy", encoding="utf-8")
        tech, owner = discover.detect_tech_stack(d)
        assert "python" in tech
        assert "fastapi" in tech
        assert owner == "backend-agent"

    def test_react_frontend(self, tmp_path: Path) -> None:
        d = tmp_path / "web"
        d.mkdir()
        (d / "package.json").write_text(
            '{"dependencies":{"react":"^18.0","next":"^14.0"},"devDependencies":{"typescript":"^5.0"}}',
            encoding="utf-8",
        )
        (d / "tsconfig.json").write_text("{}", encoding="utf-8")
        tech, owner = discover.detect_tech_stack(d)
        assert "react" in tech
        assert "nextjs" in tech
        assert "typescript" in tech
        assert owner == "frontend-agent"

    def test_express_backend(self, tmp_path: Path) -> None:
        d = tmp_path / "api"
        d.mkdir()
        (d / "package.json").write_text('{"dependencies":{"express":"^4.18"}}', encoding="utf-8")
        tech, owner = discover.detect_tech_stack(d)
        assert "express" in tech
        assert owner == "backend-agent"

    def test_terraform(self, tmp_path: Path) -> None:
        d = tmp_path / "infra"
        d.mkdir()
        (d / "main.tf").write_text('resource "aws_instance" "web" {}', encoding="utf-8")
        tech, owner = discover.detect_tech_stack(d)
        assert "terraform" in tech
        assert owner == "devops-agent"

    def test_docker_alone_no_owner(self, tmp_path: Path) -> None:
        d = tmp_path / "svc"
        d.mkdir()
        (d / "Dockerfile").write_text("FROM alpine", encoding="utf-8")
        tech, owner = discover.detect_tech_stack(d)
        assert "docker" in tech
        assert owner == ""  # Docker alone doesn't suggest an owner

    def test_unknown_tech(self, tmp_path: Path) -> None:
        d = tmp_path / "mystery"
        d.mkdir()
        (d / "main.zig").write_text("", encoding="utf-8")
        tech, owner = discover.detect_tech_stack(d)
        assert tech == []
        assert owner == ""


# ---------------------------------------------------------------------------
# OpenSpec detection
# ---------------------------------------------------------------------------


class TestOpenSpecDetection:
    def test_openspec_dir_in_repo(self, project_dir: Path) -> None:
        repo = make_git_repo(project_dir / "specs-repo")
        (repo / "openspec").mkdir()
        result = discover.detect_openspec(project_dir, [repo])
        assert result is not None
        assert result["repo"] == "specs-repo"

    def test_openspec_config_file(self, project_dir: Path) -> None:
        repo = make_git_repo(project_dir / "specs-repo")
        (repo / "openspec.config.yaml").write_text("format: openspec", encoding="utf-8")
        result = discover.detect_openspec(project_dir, [repo])
        assert result is not None

    def test_no_openspec(self, project_dir: Path) -> None:
        repo = make_git_repo(project_dir / "plain-repo")
        result = discover.detect_openspec(project_dir, [repo])
        assert result is None


# ---------------------------------------------------------------------------
# Draft generation
# ---------------------------------------------------------------------------


class TestDraftGeneration:
    def test_draft_created_and_valid(self, project_dir: Path) -> None:
        make_git_repo(project_dir / "svc-api")
        (project_dir / "svc-api" / "package.json").write_text(
            '{"dependencies":{"express":"^4.0"}}', encoding="utf-8"
        )
        make_non_git_project(project_dir / "svc-ml", "requirements.txt")
        (project_dir / "svc-ml" / "requirements.txt").write_text("torch\npandas", encoding="utf-8")

        report = discover.scan_directory(project_dir)
        draft_path = discover.generate_draft_yaml(project_dir, report)

        assert draft_path.exists()
        assert draft_path.name == "platform.yaml.draft"

        # Validate with our validator
        validate = importlib.import_module("otaman_core.validate_platform")
        import yaml

        config = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
        errors = validate.validate_builtin(config)
        assert errors == [], f"Draft validation errors: {errors}"

    def test_draft_includes_non_git_repos(self, project_dir: Path) -> None:
        make_non_git_project(project_dir / "my-app", "pyproject.toml")
        report = discover.scan_directory(project_dir)
        draft_path = discover.generate_draft_yaml(project_dir, report)

        import yaml

        config = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
        repo_names = [r["name"] for r in config["repos"]]
        assert "my-app" in repo_names

    def test_update_preserves_ownership(self, project_dir: Path) -> None:
        """Re-running discover --update keeps existing owner assignments."""
        # Initial setup: git repo
        make_git_repo(project_dir / "api")
        (project_dir / "api" / "package.json").write_text(
            '{"dependencies":{"express":"^4.0"}}', encoding="utf-8"
        )

        # Create initial config with custom owner
        import yaml

        config = {
            "project": "test",
            "version": "1.0",
            "repos": [
                {"name": "api", "path": "./api", "owner": "my-custom-agent", "tech": ["nodejs"]},
            ],
            "specs": {"format": "fallback"},
            "communication": {"bus_path": ".agents/bus", "format": "markdown"},
        }
        (project_dir / "platform.yaml").write_text(
            yaml.dump(config, default_flow_style=False), encoding="utf-8"
        )

        # Now add a new non-git project
        make_non_git_project(project_dir / "ml-svc", "requirements.txt")
        (project_dir / "ml-svc" / "requirements.txt").write_text("torch\npandas", encoding="utf-8")

        # Run update
        report = discover.scan_directory(project_dir)
        out_path, changes = discover.update_existing_config(project_dir, report)

        updated = yaml.safe_load(out_path.read_text(encoding="utf-8"))
        repos_by_name = {r["name"]: r for r in updated["repos"]}

        # Original owner preserved
        assert repos_by_name["api"]["owner"] == "my-custom-agent"
        # New repo added with suggested owner
        assert "ml-svc" in repos_by_name
        assert repos_by_name["ml-svc"]["owner"] == "data-agent"

        # Changes reported correctly
        assert "ml-svc" in changes["added"]
        assert "api" in changes["unchanged"] or any(
            u["name"] == "api" for u in changes.get("updated", [])
        )

    def test_update_detects_new_git(self, project_dir: Path) -> None:
        """After git init, re-running --update should pick up the change."""
        # Start with a non-git project
        make_non_git_project(project_dir / "svc", "pyproject.toml")

        # Create initial config
        import yaml

        report = discover.scan_directory(project_dir)
        discover.generate_draft_yaml(project_dir, report)

        # Rename draft to platform.yaml
        draft = project_dir / "platform.yaml.draft"
        config = yaml.safe_load(draft.read_text(encoding="utf-8"))
        config["repos"][0]["owner"] = "backend-agent"  # simulate user edit
        (project_dir / "platform.yaml").write_text(
            yaml.dump(config, default_flow_style=False), encoding="utf-8"
        )

        # Simulate git init
        (project_dir / "svc" / ".git").mkdir()

        # Re-scan and update
        report2 = discover.scan_directory(project_dir)
        svc_repo = next(r for r in report2["repos"] if r["name"] == "svc")
        assert svc_repo["has_git"] is True  # now detected as git

        # Update preserves the custom owner
        out_path, changes = discover.update_existing_config(project_dir, report2)
        updated = yaml.safe_load(out_path.read_text(encoding="utf-8"))
        assert updated["repos"][0]["owner"] == "backend-agent"

        # No warnings about no .git/ anymore
        no_git_warnings = [w for w in report2["warnings"] if "no .git/" in w]
        assert len(no_git_warnings) == 0

    def test_update_removed_repo_kept(self, project_dir: Path) -> None:
        """Repos in config but not on disk are flagged but kept."""
        make_git_repo(project_dir / "api")
        (project_dir / "api" / "package.json").write_text("{}", encoding="utf-8")

        import yaml

        config = {
            "project": "test",
            "version": "1.0",
            "repos": [
                {"name": "api", "path": "./api", "owner": "backend-agent"},
                {"name": "old-svc", "path": "./old-svc", "owner": "legacy-agent"},
            ],
            "specs": {"format": "fallback"},
            "communication": {"bus_path": ".agents/bus", "format": "markdown"},
        }
        (project_dir / "platform.yaml").write_text(
            yaml.dump(config, default_flow_style=False), encoding="utf-8"
        )

        report = discover.scan_directory(project_dir)
        out_path, changes = discover.update_existing_config(project_dir, report)

        updated = yaml.safe_load(out_path.read_text(encoding="utf-8"))
        names = [r["name"] for r in updated["repos"]]
        assert "old-svc" in names  # kept, not deleted
        assert "old-svc" in changes["removed"]  # flagged

    def test_draft_with_openspec(self, project_dir: Path) -> None:
        repo = make_git_repo(project_dir / "specs")
        (repo / "openspec").mkdir()
        report = discover.scan_directory(project_dir)
        draft_path = discover.generate_draft_yaml(project_dir, report)

        import yaml

        config = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
        assert config["specs"]["format"] == "openspec"
        assert config["specs"]["path"] == "./specs"


# ---------------------------------------------------------------------------
# otaman-scan-ux-hardening task 2.2 + 2.3 — spec-repo name detection +
# launcher: stub emission
# ---------------------------------------------------------------------------


class TestSpecRepoDetectionAndLauncherStub:
    def test_empty_specs_repo_detected_by_name(self, project_dir: Path) -> None:
        """An empty `<program>-specs/` with `.git/` qualifies as the specs repo."""
        # Simulate a freshly-`git init`ed but otherwise empty spec scaffold —
        # this is the case the original content-based heuristic missed.
        make_git_repo(project_dir / "foo-specs")
        # Add a sibling non-specs git repo so the report has something to
        # compare against.
        make_git_repo(project_dir / "api")
        (project_dir / "api" / "package.json").write_text("{}", encoding="utf-8")

        report = discover.scan_directory(project_dir)
        by_name = {r["name"]: r for r in report["repos"]}

        assert by_name["foo-specs"]["is_spec_repo"] is True
        assert by_name["foo-specs"]["suggested_owner"] == "spec-agent"
        # Non-specs repo unchanged
        assert by_name["api"]["is_spec_repo"] is False
        assert by_name["api"]["suggested_owner"] != "spec-agent"

    def test_spec_repo_dash_spec_suffix(self, project_dir: Path) -> None:
        """Directories ending in `-spec` (singular) also qualify."""
        make_git_repo(project_dir / "bar-spec")
        report = discover.scan_directory(project_dir)
        by_name = {r["name"]: r for r in report["repos"]}
        assert by_name["bar-spec"]["is_spec_repo"] is True
        assert by_name["bar-spec"]["suggested_owner"] == "spec-agent"

    def test_non_matching_name_not_flagged(self, project_dir: Path) -> None:
        """A `.git/`-only repo whose name doesn't match the convention stays normal."""
        # Use a name without one of scan_directory's prefix-strip prefixes
        # (repo-, service-, svc-, app-) so the report `name` equals the dir name.
        make_git_repo(project_dir / "frontend")
        report = discover.scan_directory(project_dir)
        by_name = {r["name"]: r for r in report["repos"]}
        assert by_name["frontend"]["is_spec_repo"] is False

    def test_draft_emits_launcher_stub(self, project_dir: Path) -> None:
        """generate_draft_yaml always emits a `launcher:` block on fresh draft."""
        make_git_repo(project_dir / "api")
        (project_dir / "api" / "package.json").write_text("{}", encoding="utf-8")

        report = discover.scan_directory(project_dir)
        draft_path = discover.generate_draft_yaml(project_dir, report)

        import yaml

        config = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
        assert "launcher" in config
        assert config["launcher"]["local"]["enabled"] is True
        assert config["launcher"]["ssh"]["enabled"] is False
        assert "host" in config["launcher"]["ssh"]
        assert "repo_path" in config["launcher"]["ssh"]

    def test_draft_marks_spec_repo_in_yaml(self, project_dir: Path) -> None:
        """An empty `<program>-specs/` gets `owner: spec-agent` + `is_spec_repo: true` in the draft."""
        make_git_repo(project_dir / "foo-specs")
        make_git_repo(project_dir / "api")
        (project_dir / "api" / "package.json").write_text("{}", encoding="utf-8")

        report = discover.scan_directory(project_dir)
        draft_path = discover.generate_draft_yaml(project_dir, report)

        import yaml

        config = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
        by_name = {r["name"]: r for r in config["repos"]}
        assert by_name["foo-specs"]["owner"] == "spec-agent"
        assert by_name["foo-specs"]["is_spec_repo"] is True
        # Non-spec repo doesn't carry the flag
        assert "is_spec_repo" not in by_name["api"]

    def test_update_adds_launcher_when_absent(self, project_dir: Path) -> None:
        """`scan --update` adds the launcher stub if the existing config lacks one."""
        make_git_repo(project_dir / "api")
        (project_dir / "api" / "package.json").write_text("{}", encoding="utf-8")

        import yaml

        # Existing config WITHOUT a launcher block (pre-2.3 platform.yaml shape)
        config = {
            "project": "test",
            "version": "1.0",
            "repos": [
                {"name": "api", "path": "./api", "owner": "backend-agent"},
            ],
            "specs": {"format": "fallback"},
            "communication": {"bus_path": ".agents/bus", "format": "markdown"},
        }
        (project_dir / "platform.yaml").write_text(
            yaml.dump(config, default_flow_style=False), encoding="utf-8"
        )

        report = discover.scan_directory(project_dir)
        out_path, changes = discover.update_existing_config(project_dir, report)

        updated = yaml.safe_load(out_path.read_text(encoding="utf-8"))
        assert "launcher" in updated
        assert updated["launcher"]["local"]["enabled"] is True
        # The addition is reflected in the changes summary
        assert any(c.get("name") == "(launcher)" for c in changes.get("updated", []))

    def test_update_preserves_existing_launcher(self, project_dir: Path) -> None:
        """`scan --update` does NOT overwrite an existing user-customised launcher block."""
        make_git_repo(project_dir / "api")
        (project_dir / "api" / "package.json").write_text("{}", encoding="utf-8")

        import yaml

        custom_launcher = {
            "local": {"enabled": False},  # user disabled local
            "ssh": {
                "enabled": True,  # user enabled ssh
                "host": "dev@my-real-host",  # user filled in real host
                "repo_path": "/srv/projects/api",
            },
        }
        config = {
            "project": "test",
            "version": "1.0",
            "repos": [
                {"name": "api", "path": "./api", "owner": "backend-agent"},
            ],
            "specs": {"format": "fallback"},
            "communication": {"bus_path": ".agents/bus", "format": "markdown"},
            "launcher": custom_launcher,
        }
        (project_dir / "platform.yaml").write_text(
            yaml.dump(config, default_flow_style=False), encoding="utf-8"
        )

        report = discover.scan_directory(project_dir)
        out_path, changes = discover.update_existing_config(project_dir, report)

        updated = yaml.safe_load(out_path.read_text(encoding="utf-8"))
        # User's launcher block survived intact
        assert updated["launcher"] == custom_launcher
        # No launcher entry in the changes summary
        assert not any(c.get("name") == "(launcher)" for c in changes.get("updated", []))
