#!/usr/bin/env python3
"""Bridge: runs career-ops via claude -p and returns result as text"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

CAREER_OPS_DIR = Path("/Users/lewis/Desktop/career/career-ops")
CLAUDE_BIN = "/Applications/cmux.app/Contents/Resources/bin/claude"

MODE_ALIASES = {
    "분석": "oferta",
    "analyze": "oferta",
    "analysis": "oferta",
    "oferta": "oferta",
    "딥": "deep",
    "deep": "deep",
    "company": "deep",
    "회사": "deep",
    "정보": "deep",
    "리서치": "deep",
    "contact": "contacto",
    "연락": "contacto",
    "tracker": "tracker",
    "pipeline": "pipeline",
    "pdf": "pdf",
    "apply": "apply",
    "scan": "scan",
    "batch": "batch",
    "training": "training",
    "project": "project",
    "patterns": "patterns",
    "followup": "followup",
    "ofertas": "ofertas",
}


def _resolve_claude_bin() -> str | None:
    if Path(CLAUDE_BIN).exists():
        return CLAUDE_BIN
    return shutil.which("claude")


def _run_claude(prompt: str) -> subprocess.CompletedProcess[str]:
    claude_bin = _resolve_claude_bin()
    if not claude_bin:
        raise FileNotFoundError("claude executable not found")

    return subprocess.run(
        [
            claude_bin,
            "-p",
            "--dangerously-skip-permissions",
            "--append-system-prompt",
            "Use WebFetch or WebSearch to read URLs. Do not open a browser window.",
            prompt,
        ],
        cwd=str(CAREER_OPS_DIR),
        capture_output=True,
        text=True,
        timeout=300,
    )


def _mode_system_prompt(mode: str) -> str:
    mode = (mode or "").strip()
    if mode == "oferta":
        return (
            "When evaluating a job offer, you must complete the full workflow end-to-end. "
            "Do not ask the user whether to save the report. "
            "Always write the final markdown report to reports/ and update data/applications.md before finishing. "
            "If you have enough information to draft the report, continue until the files are saved. "
            "End with a brief completion message that names the saved report path and tracker entry."
        )
    if mode == "auto-pipeline":
        return (
            "Run the full auto-pipeline end-to-end. "
            "Do not ask for permission to save. "
            "Always save the report markdown and update the tracker before finishing."
        )
    return ""


def run(mode: str, query: str = "") -> str:
    """Run a career-ops mode and return the output as text."""
    if not CAREER_OPS_DIR.exists():
        return "❌ career-ops 폴더를 찾을 수 없습니다."

    mode = (mode or "").strip()
    query = (query or "").strip()
    if not mode:
        return "❌ career-ops 모드가 비어 있습니다."

    prompt = f"/career-ops {mode}"
    if query:
        prompt = f"{prompt} {query}"

    mode_prompt = _mode_system_prompt(mode)
    if mode_prompt:
        prompt = f"{prompt}\n\n{mode_prompt}"

    try:
        last_error = ""
        for attempt in range(2):
            result = _run_claude(prompt)
            output = result.stdout.strip()
            if output:
                return output

            stderr = result.stderr.strip()
            last_error = stderr or "결과가 없습니다."
            if attempt == 0:
                time.sleep(1.5)

        return f"❌ 오류: {last_error[:500]}"
    except subprocess.TimeoutExpired:
        return "❌ 시간 초과 (5분). 다시 시도해주세요."
    except Exception as e:
        return f"❌ 실행 오류: {e}"


def analyze(query: str) -> str:
    """Compatibility wrapper for the main job-evaluation mode."""
    return run("oferta", query)


def route_command(text: str) -> tuple[str | None, str]:
    """Parse a dot command like 'deep.Company X' into (mode, query)."""
    if not text or "." not in text:
        return None, text

    prefix, remainder = text.split(".", 1)
    mode = MODE_ALIASES.get(prefix.strip().lower())
    return mode, remainder.strip()


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "Stake.com Product Manager UAE"
    print(analyze(query))
