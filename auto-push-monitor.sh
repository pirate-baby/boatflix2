#!/bin/bash

set -e

if [ $# -eq 0 ]; then
    echo "Usage: $0 <directory_1> [directory_2] ..."
    exit 1
fi

while true; do
    for dir in "$@"; do
        echo "Processing: $dir"
        cd "$dir"
        git checkout main && git push
    done
    sleep 10
done
