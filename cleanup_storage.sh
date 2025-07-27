#!/bin/bash
# cleanup_storage.sh

echo "🧹 Cleaning up storage..."

# Remove Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# Remove temporary files
rm -rf /tmp/tmp*
rm -rf /tmp/transformers_cache/*
rm -rf ~/.cache/huggingface/*

# Remove Docker cache if using Docker
docker system prune -f 2>/dev/null

echo "✅ Storage cleanup completed"
df -h
