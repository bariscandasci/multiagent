#!/bin/sh
set -eu
mkdir -p /backups
while true; do
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  tar -czf "/backups/bcd-data-${stamp}.tar.gz" -C /app data
  find /backups -type f -name 'bcd-data-*.tar.gz' -mtime +14 -delete
  sleep 86400
done
