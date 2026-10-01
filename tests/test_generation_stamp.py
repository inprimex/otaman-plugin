"""Generation stamp + the instructions-vs-generator check (ir 1.3).

The change exists because of a measured state: on 2026-09-29 every repo's
CLAUDE.local.md was last written 2026-08-28 while the generator had taken 19
commits since. The generator shipped; its output did not. cli 1.1 does the
counting and the regeneration act, deploy 1.2 wires it into upgrade paths, and
srf gains only DETECTION — this.

THE STAMP IS WRITTEN BY THE GENERATOR, not by `init --update` afterwards. cli
declined to write it (20261001T164325) and the reasoning decides it:
ce-bootstrap.sh invokes the generator directly, so a stamp applied afterwards
desynchronizes from the content the moment anyone does that. One write produces
both the body and the claim about which generator produced it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from otaman_plugin import __version__
from otaman_plugin.generate_agent_config import _build_maestro_block
from otaman_plugin.runtime_freshness import (
    INSTRUCTIONS_FILENAME,
    check_instructions_vs_generator,
)

#: cli's reader, duplicated here ONLY to assert the two agree. The
#: cross-repo test below prefers the real import when the sibling is present.
CLI_STAMP_RE = re.compile(
    r"<!--\s*otaman:generated\s+generator=(?P<version>[^\s]+)(?P<rest>[^>]*?)-->",
    re.IGNORECASE,
)

REPO = Path(__file__).resolve().parent.parent


def _block(tmp_path):
    repo = {"name": "myrepo", "path": "./myrepo", "owner": "me-agent"}
    return _build_maestro_block(repo, [repo], ".agents/bus", {"project": "t"}, tmp_path)


class TestTheGeneratorStamps:
    def test_the_managed_block_carries_a_stamp(self, tmp_path):
        assert CLI_STAMP_RE.search(_block(tmp_path))

    def test_the_stamp_names_this_generator_version(self, tmp_path):
        match = CLI_STAMP_RE.search(_block(tmp_path))
        assert match.group("version") == __version__

    def test_the_stamp_is_inside_the_managed_block(self, tmp_path):
        """Outside it, `otaman init --update` would not rewrite the stamp when
        it rewrites the content — the desync this placement prevents."""
        block = _block(tmp_path)
        begin = block.index("<!-- otaman:begin -->")
        stamp = CLI_STAMP_RE.search(block).start()
        assert begin < stamp
        assert "<!-- otaman:end -->" not in block[:stamp]

    def test_it_carries_a_timestamp_too(self, tmp_path):
        """cli tolerates extra fields; `at=` answers "does this file predate the
        generator that should have written it" without a second store."""
        match = CLI_STAMP_RE.search(_block(tmp_path))
        assert "at=" in match.group("rest")

    def test_clis_actual_reader_matches_our_stamp(self, tmp_path):
        """THE CROSS-REPO CONTRACT. Asserted against cli's real STAMP_RE, not
        my copy of it — a reader and a writer agreeing in two files that were
        never compared is how formats drift apart."""
        cli_src = REPO.parent / "otaman-cli" / "src"
        if not (cli_src / "otaman_cli" / "generated_instructions.py").is_file():
            pytest.skip("otaman-cli sibling checkout not present")
        import sys

        sys.path.insert(0, str(cli_src))
        try:
            from otaman_cli.generated_instructions import STAMP_RE
        finally:
            sys.path.remove(str(cli_src))
        match = STAMP_RE.search(_block(tmp_path))
        assert match, "cli's reporter would see no stamp in what we write"
        assert match.group("version") == __version__


class TestDetection:
    def _fleet(self, tmp_path, contents: dict[str, str | None]):
        root = tmp_path / "proj-otaman"
        root.mkdir()
        repos = []
        for name, text in contents.items():
            d = tmp_path / name
            d.mkdir()
            if text is not None:
                (d / INSTRUCTIONS_FILENAME).write_text(text, encoding="utf-8")
            repos.append({"name": name, "path": f"../{name}", "owner": f"{name}-agent"})
        (root / "platform.yaml").write_text(
            yaml.safe_dump({"project": "t", "repos": repos}), encoding="utf-8"
        )
        return root

    def test_a_matching_stamp_is_fresh(self, tmp_path):
        root = self._fleet(
            tmp_path, {"a": f"<!-- otaman:generated generator={__version__} -->\nbody"}
        )
        assert check_instructions_vs_generator(root)[0].verdict == "fresh"

    def test_an_older_stamp_is_stale(self, tmp_path):
        root = self._fleet(tmp_path, {"a": "<!-- otaman:generated generator=0.0.1 -->\nbody"})
        finding = check_instructions_vs_generator(root)[0]
        assert finding.verdict == "stale"
        assert "0.0.1" in finding.reason and __version__ in finding.reason

    def test_the_stale_reason_says_what_the_agent_is_reading(self, tmp_path):
        """A version pair alone does not tell an operator why it matters."""
        root = self._fleet(tmp_path, {"a": "<!-- otaman:generated generator=0.0.1 -->\n"})
        assert "this generator did not produce" in check_instructions_vs_generator(root)[0].reason

    def test_NO_stamp_is_not_checked_NOT_stale(self, tmp_path):
        """Absence of a stamp means provenance is UNKNOWN. Calling it stale
        asserts it was written by an older generator, which is unmeasured —
        and this is the state all 18 live files are in today."""
        root = self._fleet(tmp_path, {"a": "no stamp here\n"})
        finding = check_instructions_vs_generator(root)[0]
        assert finding.verdict == "not-checked"
        assert finding.verdict != "stale"
        assert "NOT the same as out of date" in finding.reason

    def test_a_missing_file_is_not_checked(self, tmp_path):
        root = self._fleet(tmp_path, {"a": None})
        finding = check_instructions_vs_generator(root)[0]
        assert finding.verdict == "not-checked"
        assert "never been generated for" in finding.reason

    def test_every_repo_is_reported(self, tmp_path):
        root = self._fleet(
            tmp_path,
            {
                "a": f"<!-- otaman:generated generator={__version__} -->",
                "b": "<!-- otaman:generated generator=0.0.1 -->",
                "c": "unstamped",
            },
        )
        verdicts = {
            f.subject.split(":")[1]: f.verdict for f in check_instructions_vs_generator(root)
        }
        assert verdicts == {"a": "fresh", "b": "stale", "c": "not-checked"}

    def test_extra_stamp_fields_do_not_break_the_read(self, tmp_path):
        """cli pins this tolerance; our reader must share it or a stamp one of
        us writes becomes unreadable to the other."""
        root = self._fleet(
            tmp_path,
            {
                "a": (
                    f"<!-- otaman:generated generator={__version__} "
                    "at=2026-10-01T10:00:00Z c=ab -->"
                )
            },
        )
        assert check_instructions_vs_generator(root)[0].verdict == "fresh"

    def test_unreadable_platform_yaml_is_not_checked(self, tmp_path):
        root = tmp_path / "proj-otaman"
        root.mkdir()
        (root / "platform.yaml").write_text("{[bad", encoding="utf-8")
        assert check_instructions_vs_generator(root)[0].verdict == "not-checked"


class TestWiring:
    def test_assess_runs_it(self, tmp_path):
        from otaman_plugin.runtime_freshness import assess

        root = tmp_path / "p"
        root.mkdir()
        (root / "platform.yaml").write_text(
            yaml.safe_dump({"project": "t", "repos": [{"name": "a", "path": "../a"}]}),
            encoding="utf-8",
        )
        assert any(f.check == "instructions-vs-generator" for f in assess(root))

    def test_the_round_trip_holds_end_to_end(self, tmp_path):
        """What the generator WRITES must read back as fresh. Asserting the
        emitter and the reader separately would let them drift apart while both
        test suites stayed green."""
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        root = tmp_path / "proj-otaman"
        root.mkdir()
        (root / "platform.yaml").write_text(
            yaml.safe_dump(
                {"project": "t", "repos": [{"name": "myrepo", "path": "../myrepo", "owner": "m"}]}
            ),
            encoding="utf-8",
        )
        (repo_dir / INSTRUCTIONS_FILENAME).write_text(_block(tmp_path), encoding="utf-8")
        assert check_instructions_vs_generator(root)[0].verdict == "fresh"
