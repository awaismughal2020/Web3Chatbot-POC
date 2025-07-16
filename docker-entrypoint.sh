#!/bin/bash
set -e

echo "🚀 Starting Web3 Chatbot..."

# Function to wait for service
wait_for_service() {
    local host="$1"
    local port="$2"
    local service_name="$3"
    local max_attempts=30
    local attempt=1

    echo "⏳ Waiting for $service_name at $host:$port..."

    while [ $attempt -le $max_attempts ]; do
        if nc -z "$host" "$port" 2>/dev/null; then
            echo "✅ $service_name is ready!"
            return 0
        fi

        echo "⏳ Attempt $attempt/$max_attempts - $service_name not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "❌ Failed to connect to $service_name after $max_attempts attempts"
    return 1
}

# Wait for Redis
if [ "${REDIS_HOST:-}" ]; then
    wait_for_service "${REDIS_HOST}" "${REDIS_PORT:-6379}" "Redis"
fi

# Wait for Typesense
if [ "${TYPESENSE_HOST:-}" ]; then
    wait_for_service "${TYPESENSE_HOST}" "${TYPESENSE_PORT:-8108}" "Typesense"

    # Additional check for Typesense health
    echo "🔍 Checking Typesense health..."
    max_health_checks=30
    health_check=1

    while [ $health_check -le $max_health_checks ]; do
        if curl -f "http://${TYPESENSE_HOST}:${TYPESENSE_PORT:-8108}/health" 2>/dev/null; then
            echo "✅ Typesense health check passed!"
            break
        fi

        echo "⏳ Health check $health_check/$max_health_checks - Typesense not healthy yet..."
        sleep 2
        health_check=$((health_check + 1))
    done

    if [ $health_check -gt $max_health_checks ]; then
        echo "⚠️ Typesense health check failed, but continuing..."
    fi
fi

echo "🎯 All dependencies ready, starting application..."

# Execute the main command
exec "$@"
