#!/usr/bin/env bash
set -euo pipefail

if [ -d /data ]; then
  chown -R appuser:appuser /data || true
fi

exec su -s /bin/sh appuser -c "$*"
