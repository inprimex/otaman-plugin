"""Tests for Phase 8 — domain templates, path rules, standards rendering, lifecycle gates."""

import importlib
import json
import sys
from pathlib import Path

import pytest
import yaml

# Add scripts/ to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
discover = importlib.import_module("discover_repos")
gen_config = importlib.import_module("generate_agent_config")

# platform-schema.yaml lives in otaman-core after the carve
ASSETS = Path(__file__).parent.parent.parent / "otaman-core" / "src" / "otaman_core" / "schemas"
REFERENCES = Path(__file__).parent.parent / "references"
AGENTS = Path(__file__).parent.parent / "agents"


# ---------------------------------------------------------------------------
# Schema tests — new fields
# ---------------------------------------------------------------------------

class TestPlatformSchema:
    @pytest.fixture
    def schema(self):
        return yaml.safe_load((ASSETS / "platform-schema.yaml").read_text(encoding="utf-8"))

    def test_domain_field_exists(self, schema):
        assert "domain" in schema["properties"]
        assert "healthcare" in schema["properties"]["domain"]["enum"]

    def test_lifecycle_field_exists(self, schema):
        assert "lifecycle" in schema["properties"]
        assert "phases" in schema["properties"]["lifecycle"]["properties"]
        assert "gates" in schema["properties"]["lifecycle"]["properties"]

    def test_standards_field_exists(self, schema):
        assert "standards" in schema["properties"]
        assert "repo_standards" in schema["properties"]["standards"]["properties"]
        assert "methodology" in schema["properties"]["standards"]["properties"]

    def test_knowledge_field_exists(self, schema):
        assert "knowledge" in schema["properties"]


# ---------------------------------------------------------------------------
# Standards detection
# ---------------------------------------------------------------------------

class TestStandardsDetection:
    def test_detects_pnpm(self, tmp_path):
        (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: 9")
        stds = discover.detect_standards(tmp_path)
        assert stds.get("package_manager") == "pnpm"

    def test_detects_tailwind(self, tmp_path):
        (tmp_path / "tailwind.config.ts").write_text("export default {}")
        stds = discover.detect_standards(tmp_path)
        assert stds.get("styling") == "tailwind"

    def test_detects_nextjs(self, tmp_path):
        (tmp_path / "next.config.js").write_text("module.exports = {}")
        stds = discover.detect_standards(tmp_path)
        assert stds.get("framework") == "nextjs"

    def test_detects_vitest(self, tmp_path):
        (tmp_path / "vitest.config.ts").write_text("export default {}")
        stds = discover.detect_standards(tmp_path)
        assert stds["testing"]["unit"] == "vitest"

    def test_detects_playwright(self, tmp_path):
        (tmp_path / "playwright.config.ts").write_text("export default {}")
        stds = discover.detect_standards(tmp_path)
        assert stds["testing"]["e2e"] == "playwright"

    def test_detects_eslint_prettier(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text("{}")
        (tmp_path / ".prettierrc").write_text("{}")
        stds = discover.detect_standards(tmp_path)
        assert "eslint" in stds["linting"]
        assert "prettier" in stds["linting"]

    def test_detects_typescript(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        stds = discover.detect_standards(tmp_path)
        assert stds.get("language") == "typescript"

    def test_detects_pulumi(self, tmp_path):
        (tmp_path / "Pulumi.yaml").write_text("name: test")
        stds = discover.detect_standards(tmp_path)
        assert stds.get("iac") == "pulumi"

    def test_detects_nestjs_from_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({
            "dependencies": {"@nestjs/core": "^10.0"}
        }))
        stds = discover.detect_standards(tmp_path)
        assert stds.get("framework") == "nestjs"

    def test_empty_repo(self, tmp_path):
        stds = discover.detect_standards(tmp_path)
        assert stds == {}


# ---------------------------------------------------------------------------
# Standards rendering in CLAUDE.md
# ---------------------------------------------------------------------------

class TestStandardsRendering:
    def test_renders_standards(self, tmp_path):
        config = {
            "repos": [{"name": "web", "path": "./web", "owner": "frontend-agent"}],
            "standards": {
                "repo_standards": {
                    "web": {
                        "language": "typescript",
                        "framework": "nextjs",
                        "package_manager": "pnpm",
                        "styling": "tailwind",
                        "testing": {"unit": "vitest", "e2e": "playwright", "coverage_min": 80},
                        "linting": ["eslint", "prettier"],
                        "rules": ["Server components by default"],
                    }
                },
                "methodology": ["tdd"],
            },
            "communication": {"bus_path": ".agents/bus", "format": "markdown"},
        }
        (tmp_path / "web").mkdir()
        gen_config.generate_repo_claude_md(tmp_path, config)
        content = (tmp_path / "web" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "**Framework**: nextjs" in content
        assert "**Package manager**: pnpm" in content
        assert "**Styling**: tailwind" in content
        assert "vitest for unit tests" in content
        assert "playwright for E2E" in content
        assert "coverage: 80%" in content
        assert "Server components by default" in content
        assert "**Methodology**: tdd" in content


# ---------------------------------------------------------------------------
# Domain path rules
# ---------------------------------------------------------------------------

class TestPathRules:
    @pytest.fixture(params=["healthcare", "fintech", "general"])
    def rules(self, request):
        path = REFERENCES / "path-rules" / f"{request.param}.yaml"
        assert path.exists(), f"Missing path rules: {request.param}"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return request.param, data

    def test_has_rules_list(self, rules):
        domain, data = rules
        assert "rules" in data
        assert len(data["rules"]) > 0

    def test_rules_have_path_and_items(self, rules):
        domain, data = rules
        for rule_group in data["rules"]:
            assert "path" in rule_group, f"{domain}: rule group missing path"
            assert "rules" in rule_group, f"{domain}: rule group missing rules"
            assert len(rule_group["rules"]) > 0


# ---------------------------------------------------------------------------
# Domain agent templates
# ---------------------------------------------------------------------------

class TestDomainAgentTemplates:
    def test_healthcare_compliance_officer_exists(self):
        path = AGENTS / "templates" / "healthcare" / "compliance-officer.md"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "HIPAA" in content
        assert "PHI" in content

    def test_fintech_regulatory_reviewer_exists(self):
        path = AGENTS / "templates" / "fintech" / "regulatory-reviewer.md"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "PCI" in content


# ---------------------------------------------------------------------------
# Example validation
# ---------------------------------------------------------------------------

class TestExamples:
    def test_healthcare_full_example_loads(self):
        path = Path(__file__).parent.parent / "examples" / "healthcare-full.yaml"
        assert path.exists()
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert config["domain"] == "healthcare"
        assert "lifecycle" in config
        assert "standards" in config
        assert "knowledge" in config
        assert len(config["repos"]) == 3
