#!/usr/bin/env bash

echo "🔍 서버 상태 확인..."
echo ""

# API 서버 (포트 8000)
if lsof -i :8000 >/dev/null 2>&1; then
  echo "✅ API Server (8000): RUNNING"
else
  echo "❌ API Server (8000): STOPPED"
fi

# Vite 서버 (포트 5173)
if lsof -i :5173 >/dev/null 2>&1; then
  echo "✅ Vite Server (5173): RUNNING"
else
  echo "❌ Vite Server (5173): STOPPED"
fi

echo ""

# 헬스 체크
if command -v curl >/dev/null 2>&1; then
  if curl -s http://localhost:8000/api/healthz >/dev/null 2>&1; then
    echo "✅ API Health: OK"
  else
    echo "❌ API Health: FAIL"
  fi
fi
