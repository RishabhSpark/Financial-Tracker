#!/bin/bash


APP_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BACKUP_DIR_SOURCE="$APP_DIR/backups/backup" 

BACKUP_DB_FILE="$BACKUP_DIR_SOURCE/output/database/po_database.db"
BACKUP_FORECAST_CSV="$BACKUP_DIR_SOURCE/output/processed/forecast_output.csv"
BACKUP_FORECAST_EXCEL="$BACKUP_DIR_SOURCE/output/processed/forecast_pivot.xlsx"
BACKUP_LOGS_DIR="$BACKUP_DIR_SOURCE/logs"
BACKUP_LLM_OUTPUT_DIR="$BACKUP_DIR_SOURCE/output/LLM output" 

APP_DB_FILE="$APP_DIR/output/database/po_database.db"
APP_FORECAST_CSV="$APP_DIR/output/processed/forecast_output.csv"
APP_FORECAST_EXCEL="$APP_DIR/output/processed/forecast_pivot.xlsx"
APP_LOGS_DIR="$APP_DIR/logs"
APP_LLM_OUTPUT_DIR="$APP_DIR/output/LLM output"
APP_OUTPUT_DIR="$APP_DIR/output"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_message "♻️ Restoring from backup: $BACKUP_DIR_SOURCE"

log_message "Deleting existing logs and output directories for clean restore..."
rm -rf "$APP_LOGS_DIR"
if [ $? -ne 0 ]; then
    log_message "ERROR: Failed to remove existing logs directory: $APP_LOGS_DIR"
    exit 1
fi
rm -rf "$APP_OUTPUT_DIR"
if [ $? -ne 0 ]; then
    log_message "ERROR: Failed to remove existing output directory: $APP_OUTPUT_DIR"
    exit 1
fi
log_message "Existing application directories removed."


log_message "Recreating necessary directory structure in application..."
mkdir -p "$(dirname "$APP_DB_FILE")"        
mkdir -p "$(dirname "$APP_FORECAST_CSV")"   
mkdir -p "$APP_LLM_OUTPUT_DIR"           
mkdir -p "$APP_LOGS_DIR"                   
log_message "Application directory structure recreated."


log_message "Copying logs folder..."
cp -r "$BACKUP_LOGS_DIR" "$APP_LOGS_DIR/" 2>/dev/null
if [ $? -ne 0 ]; then
    log_message "WARNING: logs folder not found or failed to copy from backup: $BACKUP_LOGS_DIR"
fi


log_message "Copying LLM output folder..."
cp -r "$BACKUP_LLM_OUTPUT_DIR" "$APP_LLM_OUTPUT_DIR/" 2>/dev/null
if [ $? -ne 0 ]; then
    log_message "WARNING: LLM output folder not found or failed to copy from backup: $BACKUP_LLM_OUTPUT_DIR"
fi

log_message "Copying po_database.db..."
cp "$BACKUP_DB_FILE" "$APP_DB_FILE" 2>/dev/null
if [ $? -ne 0 ]; then
    log_message "⚠️ po_database.db not found or failed to copy from backup: $BACKUP_DB_FILE"
fi

log_message "Copying forecast_output.csv..."
cp "$BACKUP_FORECAST_CSV" "$APP_FORECAST_CSV" 2>/dev/null
if [ $? -ne 0 ]; then
    log_message "⚠️ forecast_output.csv not found or failed to copy from backup: $BACKUP_FORECAST_CSV"
fi

log_message "Copying forecast_pivot.xlsx..."
cp "$BACKUP_FORECAST_EXCEL" "$APP_FORECAST_EXCEL" 2>/dev/null
if [ $? -ne 0 ]; then
    log_message "⚠️ forecast_pivot.xlsx not found or failed to copy from backup: $BACKUP_FORECAST_EXCEL"
fi

log_message "✅ Restore completed: backup files replaced the current ones."
exit 0