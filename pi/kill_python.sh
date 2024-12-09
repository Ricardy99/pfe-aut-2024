#!/bin/bash

# Find the process IDs of all Python processes
pids=$(ps -e | grep python | awk '{print $1}')

# Check if any Python processes were found
if [ -z "$pids" ]; then
    echo "No Python processes found."
else
    # Kill each Python process
    for pid in $pids; do
        echo "Killing Python process with PID: $pid"
        kill -9 $pid
    done
    echo "All Python processes have been terminated."
fi

#mysql -Bse 'DELETE FROM database.table WHERE filed < CURDATE()- 5'

