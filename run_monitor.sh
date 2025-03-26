#!/bin/bash

# Create logs directory if it doesn't exist
mkdir -p logs

# Get current timestamp for log file
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="logs/rcb_monitor_${TIMESTAMP}.log"

# Run the monitor in background
nohup python3 rcb_api_checker.py --team "Delhi Capitals" > "${LOG_FILE}" 2>&1 &

# Save the process ID
echo $! > monitor.pid

echo "RCB Ticket Monitor started in background"
echo "Log file: ${LOG_FILE}"
echo "Process ID: $(cat monitor.pid)"
echo "To stop the monitor, run: ./stop_monitor.sh"
