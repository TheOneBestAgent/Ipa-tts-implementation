#!/usr/bin/env bash
set -euo pipefail

if [ -z "${JOB_ID:-}" ] || [ -z "${SEG_ID:-}" ]; then
  echo "Usage: JOB_ID=... SEG_ID=... $0"
  exit 1
fi

BASE_URL="http://localhost:3000"
URL="$BASE_URL/api/tts/jobs/$JOB_ID/segments/$SEG_ID"

echo "HEAD $URL"
curl -I "$URL" | head -n 1

echo "HEAD $URL (Range: bytes=0-1023)"
curl -I -H "Range: bytes=0-1023" "$URL" | head -n 1
