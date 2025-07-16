import subprocess
import time

def run_docker_command(command):
    print(f"Running: {command}")
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        print(f"Error running: {command}")
        exit(1)
    print(f"✓ Completed: {command}\n")

# Start services one by one
print("🚀 Starting Web3 Chatbot Services...\n")

run_docker_command("docker-compose up -d redis")
time.sleep(10)

run_docker_command("docker-compose up -d typesense")
time.sleep(30)

run_docker_command("docker-compose up -d chatbot")
time.sleep(15)

print("🎉 All services started!")

