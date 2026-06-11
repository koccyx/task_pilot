"""Setup script for task_pilot with automatic virtual environment management."""

import subprocess
import sys
import venv
from pathlib import Path

from setuptools import Command, find_packages, setup


def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent


def create_venv(venv_path):
    """Create a virtual environment."""
    print(f"🔄 Creating virtual environment at {venv_path}...")
    try:
        venv.create(venv_path, with_pip=True)
        print(f"✅ Virtual environment created successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to create virtual environment: {e}")
        return False


def get_venv_python(venv_path):
    """Get the Python executable path in the virtual environment."""
    if sys.platform == "win32":
        return venv_path / "Scripts" / "python.exe"
    else:
        return venv_path / "bin" / "python"


def get_venv_pip(venv_path):
    """Get the pip executable path in the virtual environment."""
    if sys.platform == "win32":
        return venv_path / "Scripts" / "pip.exe"
    else:
        return venv_path / "bin" / "pip"


def install_in_venv(venv_path):
    """Install the package in the virtual environment."""
    python_exe = get_venv_python(venv_path)
    pip_exe = get_venv_pip(venv_path)

    if not python_exe.exists():
        print(f"❌ Python executable not found at {python_exe}")
        return False

    print(f"🔄 Installing package in virtual environment...")
    try:
        # Upgrade pip first
        subprocess.run(
            [str(python_exe), "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
            capture_output=True,
        )

        # Install the package in editable mode
        subprocess.run(
            [str(pip_exe), "install", "-e", "."],
            check=True,
            capture_output=True,
        )

        print("✅ Package installed successfully in virtual environment")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install package: {e}")
        return False


class VenvCommand(Command):
    """Custom command to create and setup virtual environment."""

    description = "Create virtual environment and install dependencies"
    user_options = [
        ("venv-path=", None, "Path to virtual environment (default: .venv)"),
        ("skip-install", None, "Skip installing the package in venv"),
    ]

    def initialize_options(self):
        self.venv_path = None
        self.skip_install = False

    def finalize_options(self):
        if self.venv_path is None:
            self.venv_path = get_project_root() / ".venv"
        else:
            self.venv_path = Path(self.venv_path)

    def run(self):
        print("🚀 Setting up virtual environment for task_pilot...")
        print("=" * 60)

        # Create virtual environment
        if not create_venv(self.venv_path):
            sys.exit(1)

        # Install package in venv
        if not self.skip_install:
            if not install_in_venv(self.venv_path):
                sys.exit(1)

        # Create .env file if it doesn't exist
        env_file = get_project_root() / ".env"
        env_example = get_project_root() / "env.example"

        if not env_file.exists() and env_example.exists():
            try:
                with open(env_example, "r") as src, open(env_file, "w") as dst:
                    dst.write(src.read())
                print("✅ Created .env file from env.example")
            except Exception as e:
                print(f"⚠️  Failed to create .env file: {e}")

        print("\n🎉 Virtual environment setup completed!")
        print(f"\n📋 Virtual environment location: {self.venv_path}")

        # Show activation instructions
        if sys.platform == "win32":
            print("\n🔧 To activate the virtual environment:")
            print(f"   {self.venv_path}\\Scripts\\activate")
        else:
            print("\n🔧 To activate the virtual environment:")
            print(f"   source {self.venv_path}/bin/activate")

        print("\n📋 Next steps:")
        print("1. Activate the virtual environment (see above)")
        print("2. Edit .env file with Telegram, AI, Kaiten and storage settings")
        print("3. Run MCP server: python -m chat_bot.mcp_server.server")
        print("4. Run bot: python -m chat_bot.bot")


class DevCommand(Command):
    """Custom command for development setup."""

    description = "Setup development environment with all tools"
    user_options = [
        ("venv-path=", None, "Path to virtual environment (default: .venv)"),
    ]

    def initialize_options(self):
        self.venv_path = None

    def finalize_options(self):
        if self.venv_path is None:
            self.venv_path = get_project_root() / ".venv"
        else:
            self.venv_path = Path(self.venv_path)

    def run(self):
        print("🔧 Setting up development environment...")

        # First run venv setup
        venv_cmd = VenvCommand(self.distribution)
        venv_cmd.venv_path = self.venv_path
        venv_cmd.run()

        # Install development dependencies
        pip_exe = get_venv_pip(self.venv_path)
        dev_deps = [
            "pytest",
            "black",
            "flake8",
            "mypy",
            "types-aiofiles",
            "aiofiles",
        ]

        print("\n🔄 Installing development dependencies...")
        try:
            for dep in dev_deps:
                subprocess.run(
                    [str(pip_exe), "install", dep],
                    check=True,
                    capture_output=True,
                )
            print("✅ Development dependencies installed")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Failed to install some dev dependencies: {e}")

        print("\n🎉 Development environment ready!")


# Read README for long description
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="task_pilot",
    version="0.0.1",
    description="Core Telegram agent for working with Kaiten via MCP",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Development Status ::Development",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.10",
    install_requires=[
        "python-telegram-bot>=21.9",
        "python-dotenv>=1.0.0",
        "langchain>=0.3.27",
        "langchain-openai>=0.3.29",
        "langgraph>=0.2.0",
        "pydantic>=2.11.7",
        "aiofiles>=23.0.0",
        "asyncpg>=0.30.0",
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "python-multipart>=0.0.6",
        "httpx>=0.28.1",
        "langchain-mcp-adapters>=0.1.0",
        "telegramify-markdown>=0.1.0",
        "fastmcp>=2.3.2",
    ],
    extras_require={
        "dev": [
            "isort",
            "black",
            "flake8",
            "mypy",
            "pylint",
            "types-aiofiles",
        ],
    },
    entry_points={
        "console_scripts": [
            "telegram-chat-logger=chat_bot.bot:main",
        ],
    },
    cmdclass={
        "venv": VenvCommand,
        "dev": DevCommand,
    },
    include_package_data=True,
    zip_safe=False,
)
