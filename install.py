#!/usr/bin/env python3
"""
Installation script for the task_pilot.
Supports both conda and venv environments.
"""

import shutil
import subprocess
import sys
from pathlib import Path


def run_command(command, description, check=True):
    """Run a command and handle errors."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=check,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"✅ {description} completed successfully")
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        return False


def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 10):
        print("❌ Python 3.10 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version}")
    return True


def check_conda_available():
    """Check if conda is available in the system."""
    result = shutil.which("conda")
    return result is not None


def setup_conda_environment():
    """Setup conda environment and install dependencies."""
    env_name = "task_pilot"

    print(f"🐍 Setting up conda environment '{env_name}'...")

    # Check if environment already exists
    result = subprocess.run(
        f"conda env list",
        shell=True,
        capture_output=True,
        text=True,
    )

    env_exists = env_name in result.stdout

    if env_exists:
        print(f"⚠️  Conda environment '{env_name}' already exists")
        print(f"📋 You can activate it with: conda activate {env_name}")
        print(f"Then install dependencies with: pip install -r requirements.txt")
        return True

    # Create conda environment
    print(f"🔄 Creating conda environment '{env_name}' with Python 3.11...")
    if not run_command(
        f"conda create -n {env_name} python=3.11 -y",
        f"Creating conda environment '{env_name}'",
        check=False,
    ):
        print("\n⚠️  Failed to create conda environment (possibly SSL/network issue)")
        print("\n💡 Try manual setup instead:")
        print(f"   1. conda create -n {env_name} python=3.11 -y --offline")
        print(f"   2. conda activate {env_name}")
        print(f"   3. pip install -r requirements.txt")
        return False

    print(f"\n✅ Conda environment '{env_name}' created successfully!")
    print(f"\n🔧 Next steps:")
    print(f"   1. Activate the environment: conda activate {env_name}")
    print(f"   2. Install dependencies: pip install -r requirements.txt")
    print(f"   3. Configure .env file")
    print(f"   4. Run: python -m chat_bot.bot")

    return True


def setup_venv_environment():
    """Setup venv environment using setup.py."""
    print("🐍 Setting up venv environment...")

    if not run_command(
        "python setup.py venv",
        "Creating virtual environment and installing dependencies",
    ):
        return False

    print("\n✅ Virtual environment setup completed!")
    print(f"\n🔧 To activate the environment, run:")
    if sys.platform == "win32":
        print("   .venv\\Scripts\\activate")
    else:
        print("   source .venv/bin/activate")

    return True


def create_env_file():
    """Create .env file if it doesn't exist."""
    env_file = Path(".env")
    if env_file.exists():
        print("✅ .env file already exists")
        return True

    env_example = Path("env.example")
    if not env_example.exists():
        print("❌ env.example file not found")
        return False

    try:
        with open(env_example, "r", encoding="utf-8") as src, open(
            env_file, "w", encoding="utf-8"
        ) as dst:
            dst.write(src.read())
        print("✅ Created .env file from env.example")
        print("⚠️  Please edit .env file and add your credentials")
        return True
    except Exception as e:
        print(f"❌ Failed to create .env file: {e}")
        return False


def main():
    """Main installation function."""
    print("🚀 Installing task_pilot...")
    print("=" * 60)

    # Check Python version
    if not check_python_version():
        sys.exit(1)

    # Create .env file first
    create_env_file()

    # Detect environment preference
    use_conda = check_conda_available()

    if use_conda:
        print("\n✨ Conda detected! Using conda for environment management.")
        print("\n💡 TIP: If you have network/SSL issues, see manual setup below.")
        print(
            "\nPress Enter to continue with automatic setup, or Ctrl+C for manual setup..."
        )

        try:
            input()
        except KeyboardInterrupt:
            print("\n\n📋 Manual Setup Instructions:")
            print("=" * 60)
            print("1. Create conda environment:")
            print("   conda create -n task_pilot python=3.11 -y")
            print("\n2. Activate the environment:")
            print("   conda activate task_pilot")
            print("\n3. Install dependencies:")
            print("   pip install -r requirements.txt")
            print("   # or")
            print("   pip install python-telegram-bot python-dotenv langchain")
            print("   pip install langchain-openai pydantic aiofiles")
            print("   pip install fastapi uvicorn")
            print("\n4. Configure .env file with your credentials")
            print("\n5. Run MCP server and bot:")
            print("   python -m chat_bot.mcp_server.server")
            print("   python -m chat_bot.bot")
            print("\n📚 For more details, see README.md")
            sys.exit(0)

        env_setup_success = setup_conda_environment()

        if not env_setup_success:
            print("\n" + "=" * 60)
            print("📋 Manual Setup Instructions (Conda with SSL issues):")
            print("=" * 60)
            print("1. Create environment:")
            print("   conda create -n task_pilot python=3.11 -y")
            print("\n2. Activate environment:")
            print("   conda activate task_pilot")
            print("\n3. Install dependencies:")
            print("   pip install -r requirements.txt")
            print("\n4. Edit .env file with your credentials")
            print("\n5. Run MCP server and bot:")
            print("   python -m chat_bot.mcp_server.server")
            print("   python -m chat_bot.bot")
            sys.exit(0)
    else:
        print("\n📦 Conda not detected.")
        print("\n💡 Manual Setup Instructions:")
        print("=" * 60)
        print("1. Create a conda environment:")
        print("   conda create -n task_pilot python=3.11")
        print("   conda activate task_pilot")
        print("\n2. Install dependencies:")
        print("   pip install -r requirements.txt")
        print("\n3. Configure .env file with your credentials")
        print("\n4. Run MCP server and bot:")
        print("   python -m chat_bot.mcp_server.server")
        print("   python -m chat_bot.bot")
        sys.exit(0)

    print("\n🎉 Setup completed!")
    print("\n📋 Next steps:")
    print("1. Activate the conda environment:")
    print("   conda activate task_pilot")
    print("\n2. Install dependencies:")
    print("   pip install -r requirements.txt")
    print("\n3. Edit .env file and add your credentials:")
    print("   - TELEGRAM_BOT_TOKEN (from @BotFather)")
    print("   - TELEGRAM_BOT_USERNAME")
    print("   - AI_API_KEY (for AI features)")
    print("   - KAITEN_API_URL")
    print("   - KAITEN_API_TOKEN")
    print("   - DATABASE_URL (for PostgreSQL storage)")
    print("\n4. Run MCP server and bot:")
    print("   python -m chat_bot.mcp_server.server")
    print("   python -m chat_bot.bot")
    print("\n📚 For more information, see README.md")


if __name__ == "__main__":
    main()
