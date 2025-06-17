#!/usr/bin/env python3
"""
Quick setup script for Web3 Fast Chatbot
Run this to automatically set up your development environment
"""

import os
import sys
import subprocess
import platform
from pathlib import Path


def print_step(step, message):
    """Print formatted step message"""
    print(f"\n🔧 Step {step}: {message}")
    print("-" * 50)


def run_command(command, description):
    """Run a shell command and handle errors"""
    print(f"Running: {command}")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        return False


def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8+ is required")
        print(f"   Current version: {version.major}.{version.minor}.{version.micro}")
        return False

    print(f"✅ Python {version.major}.{version.minor}.{version.micro} is compatible")
    return True


def check_redis():
    """Check if Redis is available"""
    print("Checking Redis availability...")

    # Try to connect to Redis
    redis_available = run_command("redis-cli ping", "Testing Redis connection")

    if not redis_available:
        print("⚠️ Redis is not running or not installed")
        print("Redis installation options:")

        system = platform.system().lower()
        if system == "darwin":  # macOS
            print("   macOS: brew install redis && brew services start redis")
        elif system == "linux":
            print("   Ubuntu/Debian: sudo apt install redis-server && sudo systemctl start redis")
            print("   CentOS/RHEL: sudo yum install redis && sudo systemctl start redis")
        elif system == "windows":
            print("   Windows: Download from https://redis.io/download")

        print("   Docker: docker run -d -p 6379:6379 redis:alpine")

        choice = input("\nWould you like to start Redis with Docker? (y/n): ").lower()
        if choice == 'y':
            return run_command("docker run -d -p 6379:6379 --name web3-chatbot-redis redis:alpine",
                               "Starting Redis with Docker")

    return redis_available


def create_env_file():
    """Create .env file from template"""
    env_template = Path(".env.template")
    env_file = Path(".env")

    if not env_template.exists():
        print("❌ .env.template not found")
        return False

    if env_file.exists():
        choice = input("📄 .env file already exists. Overwrite? (y/n): ").lower()
        if choice != 'y':
            return True

    # Copy template to .env
    with open(env_template, 'r') as template:
        content = template.read()

    with open(env_file, 'w') as env:
        env.write(content)

    print("✅ Created .env file from template")
    return True


def get_api_keys():
    """Prompt user for API keys"""
    env_file = Path(".env")

    if not env_file.exists():
        print("❌ .env file not found")
        return False

    print("\n🔑 API Key Setup")
    print("You need at least a Groq API key to get started.")
    print()

    # Get Groq API key
    groq_key = input("Enter your Groq API key (required): ").strip()
    if not groq_key:
        print("⚠️ Groq API key is required")
        print("   Get one from: https://console.groq.com/")
        return False

    # Get CoinGecko API key (optional)
    coingecko_key = input("Enter your CoinGecko API key (optional, press Enter to skip): ").strip()

    # Update .env file
    with open(env_file, 'r') as f:
        content = f.read()

    # Replace placeholder values
    content = content.replace("GROQ_API_KEY=your_groq_api_key_here", f"GROQ_API_KEY={groq_key}")

    if coingecko_key:
        content = content.replace("COINGECKO_API_KEY=your_coingecko_api_key_here", f"COINGECKO_API_KEY={coingecko_key}")

    with open(env_file, 'w') as f:
        f.write(content)

    print("✅ API keys saved to .env file")
    return True


def install_dependencies():
    """Install Python dependencies"""
    requirements_file = Path("requirements.txt")

    if not requirements_file.exists():
        print("❌ requirements.txt not found")
        return False

    print("Installing Python dependencies...")
    return run_command(f"{sys.executable} -m pip install -r requirements.txt",
                       "Installing dependencies")


def create_directories():
    """Create necessary directories"""
    directories = ["logs", "static"]

    for directory in directories:
        path = Path(directory)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            print(f"📁 Created directory: {directory}")
        else:
            print(f"📁 Directory already exists: {directory}")

    return True


def test_setup():
    """Test if setup is working"""
    print("🧪 Testing setup...")

    # Test import
    try:
        from config import settings
        print("✅ Configuration loaded successfully")

        if not settings.GROQ_API_KEY:
            print("⚠️ GROQ_API_KEY not found in environment")
            return False

        print("✅ Required API keys found")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False


def main():
    """Main setup function"""
    print("🚀 Web3 Fast Chatbot - Quick Setup")
    print("=" * 50)
    print("This script will help you set up your development environment.")

    # Step 1: Check Python version
    print_step(1, "Checking Python version")
    if not check_python_version():
        sys.exit(1)

    # Step 2: Install dependencies
    print_step(2, "Installing Python dependencies")
    if not install_dependencies():
        print("❌ Failed to install dependencies")
        sys.exit(1)

    # Step 3: Create directories
    print_step(3, "Creating necessary directories")
    create_directories()

    # Step 4: Create .env file
    print_step(4, "Setting up environment configuration")
    if not create_env_file():
        sys.exit(1)

    # Step 5: Get API keys
    print_step(5, "Configuring API keys")
    if not get_api_keys():
        print("⚠️ You can add API keys manually to the .env file later")

    # Step 6: Check Redis
    print_step(6, "Checking Redis availability")
    redis_ok = check_redis()
    if not redis_ok:
        print("⚠️ Redis is not available. The chatbot will work without caching.")

    # Step 7: Test setup
    print_step(7, "Testing configuration")
    if not test_setup():
        print("❌ Setup test failed. Please check your configuration.")
        sys.exit(1)

    # Success message
    print("\n" + "=" * 50)
    print("🎉 Setup completed successfully!")
    print("=" * 50)
    print("\nNext steps:")
    print("1. Run the chatbot: python run.py")
    print("2. Open your browser: http://localhost:8000")
    print("3. Test with: python test_chatbot.py")
    print("\n💡 Try asking: 'What is the price of Bitcoin?'")

    # Optional: Start the server
    choice = input("\nWould you like to start the chatbot now? (y/n): ").lower()
    if choice == 'y':
        print("\n🚀 Starting chatbot server...")
        run_command(f"{sys.executable} run.py", "Starting server")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Setup interrupted by user")
    except Exception as e:
        print(f"\n❌ Setup error: {e}")
        sys.exit(1)
