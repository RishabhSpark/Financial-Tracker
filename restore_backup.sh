#!/bin/bash

APP_DIR="/home/fiona/Financial-Tracker"
BACKUP_DIR="$APP_DIR/backups/backup"

echo "♻️ Restoring from latest backup..."

# 1. Delete existing files/folders
rm -f "$APP_DIR/po_database.db"
rm -f "$APP_DIR/forecast_output.csv"
rm -f "$APP_DIR/forecast_pivot.xlsx"
rm -rf "$APP_DIR/logs"
rm -rf "$APP_DIR/output"

# 2. Copy backup versions into place
cp "$BACKUP_DIR/po_database.db" "$APP_DIR/" 2>/dev/null || echo "⚠️ po_database.db not found in backup"
cp "$BACKUP_DIR/forecast_output.csv" "$APP_DIR/" 2>/dev/null || echo "⚠️ forecast_output.csv not found in backup"
cp "$BACKUP_DIR/forecast_pivot.xlsx" "$APP_DIR/" 2>/dev/null || echo "⚠️ forecast_pivot.xlsx not found in backup"
cp -r "$BACKUP_DIR/logs" "$APP_DIR/" 2>/dev/null || echo "⚠️ logs folder not found in backup"
cp -r "$BACKUP_DIR/output" "$APP_DIR/" 2>/dev/null || echo "⚠️ output folder not found in backup"

echo "✅ Restore completed: backup files replaced the current ones."
