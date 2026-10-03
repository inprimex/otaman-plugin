"""The critique dispatcher bills its own invocations (llm-router-backend 1.6).

core owns the record shape (`record_critic_cost`) and the route resolution
(`effective_route`). The dispatcher owns the invocation and its tokens, so it
owns the call — the task measured ZERO call sites fleet-wide, which makes this
the first.

Being first is why the route FORMAT matters here: later records are compared
against whatever this writes.
"""

from __future__ import annotations

import pathlib

import pytest
from otaman_core.llm_router import Route

from otaman_plugin.spec_critique_dispatch import record_critique_cost, route_id

CONFIG = {
    "agents": [
        {"name": "cto-reviewer", "route": {"family": "anthropic", "model": "claude-opus-5"}},
        {"name": "plain-agent"},
    ]
}


class TestTheRouteIsCarried:
    def test_a_resolved_route_reaches_the_record(self):
        r = record_critique_cost(
            change="demo",
            critic="cto-reviewer",
            pass_index=1,
            input_tokens=1200,
            output_tokens=340,
            usd=0.021,
            at="2026-10-03T01:20:00Z",
            platform_config=CONFIG,
        )
        assert r.route == "anthropic/claude-opus-5"

    def test_an_agent_declaring_no_route_records_None_not_a_placeholder(self):
        """core: None means the backend default with no router configured. A
        placeholder string would make 'no router' indistinguishable from a
        route literally named that."""
        r = record_critique_cost(
            change="demo",
            critic="plain-agent",
            pass_index=1,
            input_tokens=1,
            output_tokens=1,
            usd=0.0,
            at="z",
            platform_config=CONFIG,
        )
        assert r.route is None

    def test_absent_config_degrades_to_unrouted_rather_than_failing(self):
        """A cost line without its route is still worth having; losing the
        line because routing config is absent is the worse trade."""
        r = record_critique_cost(
            change="demo",
            critic="x",
            pass_index=1,
            input_tokens=1,
            output_tokens=1,
            usd=0.0,
            at="z",
        )
        assert r.route is None
        assert r.usd == 0.0 and r.critic == "x"

    def test_malformed_router_config_does_not_lose_the_record(self):
        r = record_critique_cost(
            change="demo",
            critic="x",
            pass_index=1,
            input_tokens=5,
            output_tokens=5,
            usd=0.1,
            at="z",
            platform_config={"agents": "not-a-list"},
        )
        assert r.input_tokens == 5 and r.route is None


class TestRouteRendering:
    """PROVISIONAL format, flagged to core. Rendering lives in one function so
    a core-side `Route.id` replaces one line, not a format spread across call
    sites that have already accumulated records in it."""

    def test_family_and_model(self):
        assert route_id(Route(family="anthropic", model="claude-opus-5", local=False)) == (
            "anthropic/claude-opus-5"
        )

    def test_family_alone_when_no_model(self):
        assert route_id(Route(family="local-llama", model="", local=True)) == "local-llama"

    def test_none_passes_through(self):
        assert route_id(None) is None

    def test_it_is_not_clis_display_label(self):
        """cli's AgentRoute.label is for the doctor surface and carries
        '(local)' / '(leaves tenant)'. A telemetry key must not embed a
        human-facing suffix that could change for presentation reasons."""
        rendered = route_id(Route(family="anthropic", model="m", local=True))
        assert "(" not in rendered and "local" not in rendered.split("/")[0].replace(
            "anthropic", ""
        )


class TestCoresRulesStillApply:
    """The dispatcher must not re-implement or soften core's validation."""

    def test_pass_index_cap_is_cores_and_still_bites(self):
        with pytest.raises(ValueError, match="pass_index"):
            record_critique_cost(
                change="d",
                critic="c",
                pass_index=3,
                input_tokens=0,
                output_tokens=0,
                usd=0.0,
                at="z",
            )

    def test_negative_usage_is_refused_by_core(self):
        with pytest.raises(ValueError):
            record_critique_cost(
                change="d",
                critic="c",
                pass_index=1,
                input_tokens=-1,
                output_tokens=0,
                usd=0.0,
                at="z",
            )

    def test_the_module_does_not_build_the_record_itself(self):
        """core owns the shape. Constructing CriticCost here would be a second
        home for it."""
        src = pathlib.Path(
            __import__("otaman_plugin.spec_critique_dispatch", fromlist=["x"]).__file__
        ).read_text(encoding="utf-8")
        assert "CriticCost(" not in src
        assert "record_critic_cost(" in src

    def test_route_resolution_is_cores_not_reparsed(self):
        """effective_route is the single resolution point the doctor and the
        bridge dispatch also read."""
        src = pathlib.Path(
            __import__("otaman_plugin.spec_critique_dispatch", fromlist=["x"]).__file__
        ).read_text(encoding="utf-8")
        assert "effective_route" in src
        assert '"route"' not in src, "the module parses the route field itself"
