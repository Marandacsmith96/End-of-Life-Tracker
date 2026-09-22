#!/bin/bash
# Starts the Quality-of-Life Tracker (packaged build) on a Mac.
cd "$(dirname "$0")"
xattr -dr com.apple.quarantine . 2>/dev/null
echo "Starting the Quality-of-Life Tracker. Your browser will open."
echo "Leave this window open while you use the app. Press Ctrl+C or close it to stop."
./PetQoLTracker
