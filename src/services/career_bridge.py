#!/usr/bin/env python3
"""Bridge: runs career-ops via claude -p and returns result as text"""

import shlex
import subprocess
import sys
from pathlib import Path

CAREER_OPS_DIR = Path("/Users/lewis/Desktop/career/career-ops")
CLAUDE_BIN = "/Applications/cmux.app/Contents/Resources/bin/claude"


def analyze(query: str) -> str:
    """
    Run career-ops oferta analysis on the given query text.
    Returns the analysis as a string.
    """
    if not CAREER_OPS_DIR.exists():
        return "❌ career-ops 폴더를 찾을 수 없습니다."

    prompt = f"/career-ops oferta {shlex.quote(query)}"

    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", "--dangerously-skip-permissions",
             "--append-system-prompt", "Use WebFetch or WebSearch to read URLs. Do not open a browser window.",
             prompt],
            cwd=str(CAREER_OPS_DIR),
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = result.stdout.strip()
        if not output and result.stderr:
            return f"❌ 오류: {result.stderr[:500]}"
        return output or "❌ 결과가 없습니다."
    except subprocess.TimeoutExpired:
        return "❌ 시간 초과 (5분). 다시 시도해주세요."
    except Exception as e:
        return f"❌ 실행 오류: {e}"


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "Stake.com Product Manager UAE"
    print(analyze(query))
