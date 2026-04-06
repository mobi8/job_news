#!/usr/bin/env python3
"""서비스/API 활성화 여부 및 상태 관리."""

import os
import json
from pathlib import Path
from datetime import datetime

# .env 파일 로드
env_path = Path("/Users/lewis/Desktop/agent/.env")
if env_path.exists():
    for line in env_path.read_text().strip().split("\n"):
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip()


SERVICES = {
    "openrouter_api": {
        "name": "OpenRouter API (AI 인사이트)",
        "env_var": "OPENROUTER_API_KEY",
        "required": False,
        "description": "Claude Haiku로 AI 인사이트 생성 (비용 최적화됨, 선택사항)",
    },
    "telegram": {
        "name": "Telegram 알림",
        "env_var": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
        "required": False,
        "description": "신규 공고/인사이트를 Telegram으로 발송 (선택사항)",
    },
    "scraper_rss": {
        "name": "RSS 피드 스크래핑",
        "env_var": None,
        "required": True,
        "description": "iGaming Business, Fintech News UAE RSS 수집",
    },
    "scraper_browser": {
        "name": "브라우저 자동화 (Playwright)",
        "env_var": None,
        "required": True,
        "description": "Indeed UAE, LinkedIn 직접 스크래핑 (npm playwright-core 필요)",
    },
    "sqlite_db": {
        "name": "SQLite 데이터베이스",
        "env_var": None,
        "required": True,
        "description": "공고/뉴스 영구 저장소 (jobs.sqlite3)",
    },
    "dashboard_server": {
        "name": "대시보드 HTTP 서버",
        "env_var": None,
        "required": True,
        "description": "http://127.0.0.1:8765 - 웹 UI 제공",
    },
}


def get_service_status(service_key: str) -> dict:
    """서비스 활성화 여부 확인."""
    service = SERVICES.get(service_key, {})

    if service_key == "openrouter_api":
        has_key = bool(os.getenv("OPENROUTER_API_KEY"))
        return {
            "key": service_key,
            "name": service["name"],
            "enabled": has_key,
            "description": service["description"],
            "details": "API 키 설정됨" if has_key else "API 키 없음 (캐시 사용)",
        }

    elif service_key == "telegram":
        has_bot = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
        has_chat = bool(os.getenv("TELEGRAM_CHAT_ID"))
        enabled = has_bot and has_chat
        return {
            "key": service_key,
            "name": service["name"],
            "enabled": enabled,
            "description": service["description"],
            "details": f"Bot: {'✓' if has_bot else '✗'} Chat: {'✓' if has_chat else '✗'}",
        }

    elif service_key == "sqlite_db":
        db_path = Path("/Users/lewis/Desktop/agent/outputs/jobs.sqlite3")
        exists = db_path.exists()
        return {
            "key": service_key,
            "name": service["name"],
            "enabled": exists,
            "description": service["description"],
            "details": f"크기: {db_path.stat().st_size / 1024 / 1024:.1f}MB" if exists else "아직 생성 안됨",
        }

    elif service_key == "scraper_browser":
        try:
            import subprocess
            result = subprocess.run(
                ["npm", "list", "playwright-core"],
                cwd="/Users/lewis/Desktop/agent",
                capture_output=True,
                timeout=5,
            )
            enabled = result.returncode == 0
        except Exception:
            enabled = False
        return {
            "key": service_key,
            "name": service["name"],
            "enabled": enabled,
            "description": service["description"],
            "details": "npm install 완료됨" if enabled else "npm install 필요",
        }

    elif service_key == "dashboard_server":
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("127.0.0.1", 8765))
            sock.close()
            enabled = result == 0
        except Exception:
            enabled = False
        return {
            "key": service_key,
            "name": service["name"],
            "enabled": enabled,
            "description": service["description"],
            "details": "http://127.0.0.1:8765 응답 중" if enabled else "시작해야 함",
        }

    else:
        return {
            "key": service_key,
            "name": service["name"],
            "enabled": True,
            "description": service["description"],
            "details": "(기본 필수 서비스)",
        }


def get_all_status() -> dict:
    """모든 서비스 상태 반환."""
    statuses = []
    for key in SERVICES.keys():
        statuses.append(get_service_status(key))

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "services": statuses,
        "summary": {
            "total": len(statuses),
            "enabled": sum(1 for s in statuses if s["enabled"]),
            "critical": sum(1 for k in statuses if SERVICES[k["key"]].get("required")),
        },
    }


if __name__ == "__main__":
    import sys
    status = get_all_status()

    if len(sys.argv) > 1 and sys.argv[1] == "json":
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        # 텍스트 출력
        print("\n=== 서비스 상태 ===\n")
        for svc in status["services"]:
            check = "✓" if svc["enabled"] else "✗"
            print(f"{check} {svc['name']}")
            print(f"  {svc['details']}")
            print()
