#!/bin/bash

if [ -f monitor.pid ]; then
    PID=$(cat monitor.pid)
    echo "Stopping RCB Ticket Monitor (PID: $PID)..."
    kill $PID
    rm monitor.pid
    echo "Monitor stopped successfully"
else
    echo "No monitor process found"
fi
