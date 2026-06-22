#!/usr/bin/env python3
"""Fast PTY verifier for Motoko issue #1.

This command is intentionally narrower than the full TTY regression suite.  It
is the bounty acceptance probe: one stdlib-only command, synthetic isolated
state, real pseudo-terminal input, compact JSON output, and nonzero exit on
rejection.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TTY_HELPERS = REPO_ROOT / "tests" / "motoko_tty.py"
SCHEMA = "motoko-bounty-verification-v1"
ISSUE = 1
SAMPLES = 100
SHORT_P95_LIMIT_MS = 30.0
LONG_P95_LIMIT_MS = 40.0
BACKGROUND_P95_LIMIT_MS = 50.0
BACKGROUND_MAX_LIMIT_MS = 250.0
BACKGROUND_STALL_LIMIT_MS = 1600.0
MAX_TRANSCRIPT_GROWTH_MS = 10.0


def load_tty_helpers():
    spec = importlib.util.spec_from_file_location("motoko_tty_helpers", TTY_HELPERS)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load PTY helper module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def measurement_text() -> str:
    base = "ascii latency Café mañana résumé 東京界 Привет alpha beta "
    text = (base * ((SAMPLES // len(base)) + 2))[:SAMPLES]
    if len(text) != SAMPLES:
        raise RuntimeError("measurement text length mismatch")
    if not any(ord(char) > 127 for char in text):
        raise RuntimeError("measurement text lacks multibyte characters")
    return text


def scenario_metrics(row: dict) -> dict:
    return {
        "samples": int(row.get("samples", 0) or 0),
        "p50_ms": float(row.get("p50_ms", 0.0) or 0.0),
        "p95_ms": float(row.get("p95_ms", 0.0) or 0.0),
        "max_ms": float(row.get("max_ms", 0.0) or 0.0),
    }


def background_metrics(row: dict) -> dict:
    return {
        "phase": str(row.get("phase", "")),
        "samples": int(row.get("samples", 0) or 0),
        "p50_ms": float(row.get("p50_ms", 0.0) or 0.0),
        "p95_ms": float(row.get("p95_ms", 0.0) or 0.0),
        "max_ms": float(row.get("max_ms", 0.0) or 0.0),
        "longest_stall_ms": float(row.get("longest_stall_ms", 0.0) or 0.0),
        "visible_before_phase_end": bool(row.get("visible_before_phase_end")),
        "input_integrity": bool(row.get("input_integrity")),
        "background_completed": bool(row.get("background_completed")),
    }


def verify() -> dict:
    helpers = load_tty_helpers()
    motoko = helpers.load_motoko()
    text = measurement_text()

    helpers.run_tui_latency_probe(
        motoko,
        name="bounty-warmup",
        text=text[:32],
        width=140,
        transcript_pairs=2,
        burst=True,
    )
    short = helpers.run_tui_latency_probe(
        motoko,
        name="bounty-short",
        text=text,
        width=140,
        transcript_pairs=3,
        burst=True,
    )
    long = helpers.run_tui_latency_probe(
        motoko,
        name="bounty-long",
        text=text,
        width=140,
        transcript_pairs=900,
        burst=True,
    )
    background_text = "background study input Café mañana résumé 東京界 Привет "[:72]
    background = helpers.run_background_study_latency_probe(
        motoko,
        text=background_text,
        width=140,
    )

    failure_reasons: list[str] = []
    for label, row in (("short_transcript", short), ("long_transcript", long)):
        if row.get("errors"):
            failure_reasons.append(f"{label}: verifier scenario reported errors")
        if int(row.get("samples", 0) or 0) != SAMPLES:
            failure_reasons.append(f"{label}: expected {SAMPLES} samples")
        if row.get("final_input") != text or row.get("expected_input") != text:
            failure_reasons.append(f"{label}: final composer contents did not match expected input")
        if row.get("output_contains_final") is not True:
            failure_reasons.append(f"{label}: final composer output was not observed")
        if int(row.get("transcript_iterations", 0) or 0) != 0:
            failure_reasons.append(f"{label}: ordinary input scanned transcript rows")

    short_metrics = scenario_metrics(short)
    long_metrics = scenario_metrics(long)
    input_integrity = short.get("final_input") == text and long.get("final_input") == text
    unicode_fragments = ("Café", "mañana", "résumé", "東京", "界", "Привет")
    unicode_integrity = all(fragment in short.get("final_input", "") for fragment in unicode_fragments) and all(
        fragment in long.get("final_input", "") for fragment in unicode_fragments
    )

    if not input_integrity:
        failure_reasons.append("exact input integrity failed")
    if not unicode_integrity:
        failure_reasons.append("unicode integrity failed")
    if short_metrics["p95_ms"] > SHORT_P95_LIMIT_MS:
        failure_reasons.append(f"short_transcript p95 exceeded {SHORT_P95_LIMIT_MS:g} ms")
    if long_metrics["p95_ms"] > LONG_P95_LIMIT_MS:
        failure_reasons.append(f"long_transcript p95 exceeded {LONG_P95_LIMIT_MS:g} ms")
    if long_metrics["p95_ms"] - short_metrics["p95_ms"] > MAX_TRANSCRIPT_GROWTH_MS:
        failure_reasons.append("long transcript materially increased p95 latency")
    background_report = background_metrics(background)
    if background.get("errors"):
        failure_reasons.append("background_study: verifier scenario reported errors")
    if background_report["samples"] != len(background_text):
        failure_reasons.append(f"background_study: expected {len(background_text)} samples")
    if not background_report["visible_before_phase_end"]:
        failure_reasons.append("background_study: input was withheld until the background phase ended")
    if not background_report["input_integrity"]:
        failure_reasons.append("background_study: exact input integrity failed")
    if not background_report["background_completed"]:
        failure_reasons.append("background_study: synthetic evidence-store work did not complete")
    if background_report["p95_ms"] > BACKGROUND_P95_LIMIT_MS:
        failure_reasons.append(f"background_study p95 exceeded {BACKGROUND_P95_LIMIT_MS:g} ms")
    if background_report["max_ms"] > BACKGROUND_MAX_LIMIT_MS:
        failure_reasons.append(f"background_study max exceeded {BACKGROUND_MAX_LIMIT_MS:g} ms")
    if background_report["longest_stall_ms"] > BACKGROUND_STALL_LIMIT_MS:
        failure_reasons.append(f"background_study visible-progress stall exceeded {BACKGROUND_STALL_LIMIT_MS:g} ms")

    return {
        "schema": SCHEMA,
        "issue": ISSUE,
        "accepted": not failure_reasons,
        "short_transcript": short_metrics,
        "long_transcript": long_metrics,
        "background_study": background_report,
        "input_integrity": input_integrity,
        "unicode_integrity": unicode_integrity,
        "failure_reasons": failure_reasons,
    }


def rejected_report(reason: str) -> dict:
    return {
        "schema": SCHEMA,
        "issue": ISSUE,
        "accepted": False,
        "short_transcript": {"samples": 0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0},
        "long_transcript": {"samples": 0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0},
        "background_study": {
            "phase": "study: evidence-store",
            "samples": 0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "max_ms": 0.0,
            "longest_stall_ms": 0.0,
            "visible_before_phase_end": False,
            "input_integrity": False,
            "background_completed": False,
        },
        "input_integrity": False,
        "unicode_integrity": False,
        "failure_reasons": [reason],
    }


def main() -> int:
    try:
        report = verify()
    except Exception as exc:
        report = rejected_report(f"verification could not complete: {type(exc).__name__}")
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("accepted") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
