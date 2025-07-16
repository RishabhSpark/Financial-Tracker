#!/bin/bash

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKUP_DIR="$APP_DIR/backups"
DEST="$BACKUP_DIR/backup" 

rm -rf "$DEST"

mkdir -p "$DEST"

echo "📦 Backing up to: $DEST"

cp -r "$APP_DIR/output" "$DEST/"

cp -r "$APP_DIR/logs" "$DEST/"

echo "✅ Backup completed at $DEST"