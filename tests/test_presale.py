"""Tests for pre-sale infrastructure — init-presale.py, schemas, component library."""

import importlib
import sys
from pathlib import Path

import pytest
import yaml

# Add scripts/ to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
init_presale = importlib.import_module("otaman_plugin.init_presale")

ASSETS = Path(__file__).parent.parent / "assets"


# ---------------------------------------------------------------------------
# init-presale.py tests
# ---------------------------------------------------------------------------


class TestInitPresale:
    def test_creates_directory_structure(self, tmp_path):
        created = init_presale.create_presale_dir(
            tmp_path, "TEST-EST-260327", "Test Project", "healthcare", client="Acme"
        )
        assert (tmp_path / ".otaman-presale").is_dir()
        assert (tmp_path / ".otaman-presale" / "estimation").is_dir()
        assert (tmp_path / ".otaman-presale" / "architecture").is_dir()
        assert (tmp_path / ".otaman-presale" / "discovery" / "decisions").is_dir()
        assert len(created) > 0

    def test_creates_project_meta(self, tmp_path):
        init_presale.create_presale_dir(
            tmp_path, "HLT-EST-260327", "Health App", "healthcare", client="Hospital Inc"
        )
        meta_path = tmp_path / ".otaman-presale" / "project-meta.yaml"
        assert meta_path.exists()
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        assert meta["project_code"] == "HLT-EST-260327"
        assert meta["project_name"] == "Health App"
        assert meta["domain"] == "healthcare"
        assert meta["current_phase"] == "presale"
        assert meta["client"] == "Hospital Inc"
        assert len(meta["phase_history"]) == 1
        assert meta["phase_history"][0]["phase"] == "presale"
        assert meta["phase_history"][0]["completed"] is None

    def test_creates_empty_registers(self, tmp_path):
        init_presale.create_presale_dir(tmp_path, "TEST-EST-260327", "Test", "general")
        assumptions = yaml.safe_load(
            (tmp_path / ".otaman-presale" / "assumptions.yaml").read_text(encoding="utf-8")
        )
        assert assumptions["assumptions"] == []
        risks = yaml.safe_load(
            (tmp_path / ".otaman-presale" / "risks.yaml").read_text(encoding="utf-8")
        )
        assert risks["risks"] == []

    def test_idempotent_no_overwrite(self, tmp_path):
        init_presale.create_presale_dir(tmp_path, "TEST-EST-260327", "Test", "general")
        # Modify meta
        meta_path = tmp_path / ".otaman-presale" / "project-meta.yaml"
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        meta["custom_field"] = "should survive"
        with open(meta_path, "w") as f:
            yaml.dump(meta, f)

        # Re-run — should not overwrite
        init_presale.create_presale_dir(tmp_path, "NEW-CODE", "New Name", "fintech")
        meta_after = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        assert meta_after["project_code"] == "TEST-EST-260327"  # NOT overwritten
        assert meta_after["custom_field"] == "should survive"

    def test_client_optional(self, tmp_path):
        init_presale.create_presale_dir(tmp_path, "TEST-EST-260327", "Test", "general")
        meta = yaml.safe_load(
            (tmp_path / ".otaman-presale" / "project-meta.yaml").read_text(encoding="utf-8")
        )
        assert "client" not in meta


# ---------------------------------------------------------------------------
# Component library tests
# ---------------------------------------------------------------------------


class TestComponentLibrary:
    @pytest.fixture
    def library(self):
        return yaml.safe_load((ASSETS / "component-library.yaml").read_text(encoding="utf-8"))

    def test_has_required_categories(self, library):
        categories = list(library["components"].keys())
        for expected in ["auth", "api", "integrations", "infrastructure", "compliance"]:
            assert expected in categories, f"Missing category: {expected}"

    def test_components_have_hours(self, library):
        for cat_name, cat in library["components"].items():
            for var_name, var_data in cat.items():
                assert "hours" in var_data or "notes" in var_data, (
                    f"{cat_name}.{var_name} missing hours or notes"
                )

    def test_hours_are_ranges(self, library):
        for cat_name, cat in library["components"].items():
            for var_name, var_data in cat.items():
                if "hours" in var_data:
                    h = var_data["hours"]
                    assert isinstance(h, list) and len(h) == 2, (
                        f"{cat_name}.{var_name} hours should be [min, max]"
                    )
                    assert h[0] <= h[1], f"{cat_name}.{var_name} min > max"


# ---------------------------------------------------------------------------
# Estimation benchmarks tests
# ---------------------------------------------------------------------------


class TestEstimationBenchmarks:
    @pytest.fixture
    def benchmarks(self):
        return yaml.safe_load((ASSETS / "estimation-benchmarks.yaml").read_text(encoding="utf-8"))

    def test_has_required_sections(self, benchmarks):
        assert "benchmarks" in benchmarks
        assert "patterns" in benchmarks
        assert "adjustment_factors" in benchmarks

    def test_adjustment_factors_structure(self, benchmarks):
        af = benchmarks["adjustment_factors"]
        assert "domain_adjustments" in af
        assert "team_adjustments" in af
        assert "common_underestimates" in af


# ---------------------------------------------------------------------------
# Presale schema tests
# ---------------------------------------------------------------------------


class TestPresaleSchema:
    @pytest.fixture
    def schema(self):
        return yaml.safe_load((ASSETS / "presale-schema.yaml").read_text(encoding="utf-8"))

    def test_required_fields(self, schema):
        assert "project_code" in schema["properties"]
        assert "project_name" in schema["properties"]
        assert "domain" in schema["properties"]
        assert "current_phase" in schema["properties"]

    def test_valid_domains(self, schema):
        domains = schema["properties"]["domain"]["enum"]
        for expected in ["healthcare", "fintech", "marketplace", "ml-ai", "saas"]:
            assert expected in domains

    def test_valid_phases(self, schema):
        phases = schema["properties"]["current_phase"]["enum"]
        for expected in ["presale", "discovery", "development", "support", "archived"]:
            assert expected in phases


# ---------------------------------------------------------------------------
# Domain expert tests
# ---------------------------------------------------------------------------


class TestDomainExperts:
    EXPERTS_DIR = Path(__file__).parent.parent / "references" / "domain-experts"

    @pytest.fixture(
        params=["healthcare", "fintech", "marketplace", "ml-ai", "saas", "ecommerce", "iot"]
    )
    def expert_content(self, request):
        path = self.EXPERTS_DIR / f"{request.param}.md"
        assert path.exists(), f"Missing domain expert: {request.param}"
        return request.param, path.read_text(encoding="utf-8")

    def test_has_required_sections(self, expert_content):
        domain, content = expert_content
        for section in [
            "Requirements Checklist",
            "Compliance Frameworks",
            "Estimation Adjustments",
            "Risk Patterns",
        ]:
            assert section in content, f"{domain} expert missing section: {section}"
