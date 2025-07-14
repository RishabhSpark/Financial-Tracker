#!/bin/bash
APP_DIR="/home/fiona/Financial-Tracker"
BACKUP_DIR="$APP_DIR/backups"
TIMESTAMP=$(date +"%F_%H_%M")
DEST="$BACKUP_DIR/backup"

rm -rf "$DEST"
mkdir -p "$DEST"

echo "📦 Backing up to: $DEST"

cp -r "$APP_DIR/output" "$DEST/" 
cp "$APP_DIR/forecast_output.csv" "$DEST/"
cp "$APP_DIR/forecast_pivot.xlsx" "$DEST/" 
cp "$APP_DIR/po_database.db" "$DEST/" 
cp -r "$APP_DIR/logs" "$DEST/" 

echo "✅ Backup completed at $DEST"


# TODO: Restore( Button on the dashboard -> Restore backup -> Fetch from server (Optional) -> Update /backups -> Update existing files)
