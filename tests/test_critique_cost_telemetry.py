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

from otaman_plugin.spec_critique_dispatch import record_critique_cost

REPO = pathlib.Path(__file__).resolve().parent.parent

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


def _cost(local: bool, critic: str = "c"):
    cfg = {
        "agents": [
            {
                "name": "c",
                "route": {"family": "anthropic", "model": "claude-opus-5", "local": local},
            }
        ]
    }
    return record_critique_cost(
        change="d",
        critic=critic,
        pass_index=1,
        input_tokens=1,
        output_tokens=1,
        usd=0.0,
        at="z",
        platform_config=cfg,
    )


class TestTheKeyIsCoresNotMine:
    """core owns the telemetry route key (`Route.id`, core #121 / lrb 1.7).

    My 1.6 shipped a provisional `family/model` renderer, flagged as mine, and
    asked core to ratify or replace it. They replaced AND corrected it: `local`
    belongs in the key, because the same family/model run locally versus
    off-tenant are different routes for cost and sensitivity (gate 2.1). My
    renderer collapsed them — every local invocation would have billed against
    the off-tenant key.

    core then asked for the wrapper to go entirely (20261003T022741): a helper
    that still looks like a formatter is the drift seed, because the next
    person edits the helper rather than the type.
    """

    def test_local_and_off_tenant_are_DIFFERENT_keys(self):
        """The correction itself. Same family/model, different route."""
        off, local = _cost(local=False).route, _cost(local=True).route
        assert off != local, "a local route bills against the off-tenant key"
        assert local.endswith("@local")

    def test_the_key_is_exactly_what_core_renders(self):
        """Identity with `Route.id`, not equality with a hand-written string —
        a renderer that happens to agree today is the drift this replaced."""
        from otaman_core.llm_router import Route

        assert _cost(local=True).route == Route("anthropic", "claude-opus-5", True).id
        assert _cost(local=False).route == Route("anthropic", "claude-opus-5", False).id

    def test_no_wrapper_survives(self):
        """core's ask: inline `.id`, delete the helper. A wrapper is where the
        formatting creeps back."""
        import otaman_plugin.spec_critique_dispatch as m

        assert not hasattr(m, "route_id"), "the route_id wrapper is back"

    def test_a_core_predating_Route_id_yields_None_not_a_crash(self, monkeypatch):
        """`.id` must be INSIDE the try. A core predating #121 raises
        AttributeError there and must land on None — not propagate, and not
        fall back to a hand-rolled key that would COLLIDE with core's once the
        bundle catches up (a local invocation under the off-tenant key).

        This test was dropped when the route_id helper was deleted, and a
        sabotage moving `.id` outside the try then scored 12/12. Re-added
        through the real call path rather than against a helper.
        """
        import otaman_core.llm_router as lr

        class PreId:
            family, model, local = "anthropic", "claude-opus-5", True

        monkeypatch.setattr(lr, "effective_route", lambda cfg, agent: PreId())
        r = record_critique_cost(
            change="d",
            critic="c",
            pass_index=1,
            input_tokens=7,
            output_tokens=3,
            usd=0.5,
            at="z",
            platform_config={"agents": [{"name": "c"}]},
        )
        assert r.route is None, "a pre-#121 core produced a route key anyway"
        assert r.input_tokens == 7 and r.usd == 0.5, "the cost record was lost"

    def test_the_key_is_CONSUMED_not_recomputed(self, monkeypatch):
        """cli's catch (20261003T020223): comparing the key against a real
        `Route` is VACUOUS, because any recomputation reproduces that form
        exactly. Two of cli's five sabotages passed on exactly this blindness.

        So: a route whose `.id` is deliberately NOT derivable from its fields.
        Only consuming core's id can produce it; every renderer, mine included,
        fails here.
        """
        import otaman_core.llm_router as lr

        class OpaqueId:
            family, model, local = "ollama", "llama3", True
            id = "core-says-this-is-the-key"

        monkeypatch.setattr(lr, "effective_route", lambda cfg, agent: OpaqueId())
        r = record_critique_cost(
            change="d",
            critic="c",
            pass_index=1,
            input_tokens=7,
            output_tokens=3,
            usd=0.5,
            at="z",
            platform_config={"agents": [{"name": "c"}]},
        )
        assert r.route == "core-says-this-is-the-key", (
            "the key was recomputed from the route's fields, not read off core's .id"
        )

    def test_no_hand_formatted_route_key_anywhere_in_the_plugin(self):
        """spec-agent's 2.1 grep-guard, implemented: no call site builds a
        route key by hand. `llm_router` is the only place that may."""
        import re

        offenders = []
        for path in (REPO / "src").rglob("*.py"):
            body = path.read_text(encoding="utf-8")
            for pattern in (r"\{family\}/\{model\}", r"\{[a-z_]*\.family\}/", r'"@local"'):
                if re.search(pattern, body):
                    offenders.append(f"{path.name}: {pattern}")
        assert not offenders, f"hand-formatted route keys: {offenders}"


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
