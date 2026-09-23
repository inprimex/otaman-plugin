"""shared-agent-memory 1.4 — the generated instruction set gains a knowledge
WRITE duty and a check-otaman-first guard, and stops advertising two surfaces
that never had a writer.

The change's own measurement is what these tests defend. `.agents/knowledge/`
existed, was advertised in every generated CLAUDE.md ("check for tech docs
relevant to your work"), and held **zero files** after months of operation — no
writer existed anywhere and no instruction told any agent to write one. On
2026-09-21 four silent-failure findings were each re-derived from scratch by
agents with nowhere to record or look, several of them rediscoveries of
weeks-old conditions. Read-only advertising is what produced that.

`.agents/proposals/` and `.agents/decisions/` were the same defect one step
further along: created by the generator, named in the instructions, never
written to by anything. D2 retires them rather than giving them writers — a
ruling IS durable knowledge (`type: decision` with its approval stem as
anchor), and proposals already live on the bus plus the SLE ledger.

WHY THE RETIREMENT IS TESTED ACROSS THE WHOLE PLUGIN, not just the generator:
deleting the two `mkdir` calls while leaving eight assets still instructing
agents to WRITE there would have been strictly worse than doing nothing. It
converts a useless-but-harmless empty directory into a write to a path that
does not exist — the precise silent-failure class this program spent
`no-silent-success` removing. So `test_no_asset_still_directs_a_write_to_a_
retired_surface` sweeps every shipped asset, not just the file that changed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import otaman_plugin.generate_agent_config as gen

REPO = Path(__file__).parent.parent

#: Everything Claude Code actually loads from this plugin. A retired surface
#: surviving in any of these still reaches an agent as an instruction.
ASSET_DIRS = ("src", "commands", "skills", "agents", "hooks", "scripts", "references")

RETIRED = (".agents/proposals", ".agents/decisions")

#: A line that merely RECORDS the retirement is fine and in fact wanted; a line
#: that still tells someone to use the surface is the defect.
_RETIREMENT_NOTE = re.compile(r"retired|NOT created|Do NOT create", re.IGNORECASE)


def _asset_files() -> list[Path]:
    out: list[Path] = []
    for d in ASSET_DIRS:
        for p in (REPO / d).rglob("*"):
            if p.is_file() and p.suffix in {".md", ".py", ".sh", ".yaml", ".yml", ".json"}:
                out.append(p)
    return out


class TestRetiredSurfaces:
    def test_generator_no_longer_creates_them(self, tmp_path):
        created = gen.create_directories(tmp_path, {})
        for retired in ("proposals", "decisions"):
            assert not (tmp_path / ".agents" / retired).exists(), (
                f".agents/{retired}/ was recreated — D2 retires it, and an "
                f"advertised surface with no writer is a conformance defect"
            )
            assert not any(retired in c for c in created)

    def test_the_surfaces_that_do_have_writers_are_untouched(self, tmp_path):
        """The retirement must be surgical. queue/, blocked/ and reviews/ all
        have real writers and must survive."""
        gen.create_directories(tmp_path, {})
        for kept in ("queue", "blocked", "reviews/pending", "reviews/done"):
            assert (tmp_path / ".agents" / kept).is_dir(), f".agents/{kept}/ went missing"

    def test_no_asset_still_directs_a_write_to_a_retired_surface(self):
        """The sweep that makes the retirement safe rather than harmful."""
        offenders: list[str] = []
        for path in _asset_files():
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if any(r in line for r in RETIRED) and not _RETIREMENT_NOTE.search(line):
                    offenders.append(f"{path.relative_to(REPO)}:{n}: {line.strip()[:90]}")
        assert not offenders, (
            "these still point an agent at a directory the generator no longer "
            "creates:\n  " + "\n  ".join(offenders)
        )


class TestGeneratedInstructions:
    """The rendered CLAUDE.local.md body, which is what an agent actually reads."""

    @pytest.fixture
    def rendered(self) -> str:
        src = (REPO / "src" / "otaman_plugin" / "generate_agent_config.py").read_text(
            encoding="utf-8"
        )
        return src

    def test_write_duty_sits_beside_the_read_instruction(self, rendered):
        """D3 is explicit that the write duty goes *beside* the existing read
        instruction. Apart, the read instruction keeps its current meaning —
        'someone else fills this in' — which is the belief being corrected."""
        read_at = rendered.index(".agents/knowledge/` exists, check for tech docs")
        write_at = rendered.index("Knowledge — you are a writer, not just a reader")
        assert 0 < write_at - read_at < 1200, (
            "the write duty drifted away from the read instruction it qualifies"
        )

    def test_write_duty_is_priced_to_the_moment_not_a_schedule(self, rendered):
        """D3's actual content. A generated 'keep the knowledge base updated'
        chore produces filler; the duty is scoped to the moment a durable fact
        is paid for, and the instruction has to say which moments those are."""
        assert "durable fact is paid for" in rendered
        for moment in ("incident diagnosed", "constraint measured", "pattern ruled"):
            assert moment in rendered, f"the instruction does not name {moment!r}"
        assert "no scheduled" in rendered.lower()

    def test_review_duty_points_at_the_actionable_list(self, rendered):
        """cli-agent's note (20260923T190443): plain `list` shows everything,
        `--past-due` shows what actually needs acting on. A review duty that
        points at the former is aspirational; one that points at the latter is
        actionable."""
        assert "--past-due" in rendered, "the review duty must name the flag that filters"

    def test_review_duty_warns_that_empty_and_none_overdue_differ(self, rendered):
        """An agent reading 'nothing overdue' must not read it the same way as
        'nothing recorded'. The second means the write duty above has stopped
        happening — which is the failure this whole change exists to prevent,
        and it is invisible if the two states are read alike. (cli renders both
        identically today; reported 20260923T191515.)"""
        assert "nothing recorded" in rendered.lower(), (
            "the instruction does not distinguish an empty filter from an empty surface"
        )

    def test_entries_require_an_evidence_anchor(self, rendered):
        assert "evidence anchor" in rendered
        assert "refused" in rendered, "an unanchored entry is refused, not quietly accepted"

    def test_check_otaman_first_names_all_three_surfaces(self, rendered):
        """The guard is only actionable if it says WHERE to look."""
        assert "Check otaman first" in rendered
        for surface in ("otaman help", "platform schema", ".agents/"):
            assert surface in rendered, f"the guard does not name {surface!r}"

    def test_guard_carries_the_incident_that_paid_for_it(self, rendered):
        """A rule with its incident attached survives contact with a deadline;
        a bare prohibition gets rationalised around. The trigger was a
        hand-rolled git credential helper built beside the existing
        connections layer."""
        assert "credential" in rendered
        assert "call site" in rendered, "the connections layer's call-site pattern is the fix"
        assert "never persist" in rendered.lower()
