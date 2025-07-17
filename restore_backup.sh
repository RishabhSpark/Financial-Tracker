#!/bin/bash

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR_SOURCE="$APP_DIR/backups/backup"

APP_OUTPUT_DIR="$APP_DIR/output"
BACKUP_OUTPUT_DIR="$BACKUP_DIR_SOURCE/output"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_message "♻️ Restoring from backup: $BACKUP_DIR_SOURCE"

log_message "Deleting contents of output directory for clean restore..."
rm -rf "$APP_OUTPUT_DIR"/*

log_message "Copying output folder from backup..."
cp -r "$BACKUP_OUTPUT_DIR/"* "$APP_OUTPUT_DIR/"

log_message "Setting ownership of restored files to $USER..."
chown -R "$USER":"$USER" "$APP_OUTPUT_DIR"

log_message "✅ Restore completed: backup folders replaced the current ones."
exit 0