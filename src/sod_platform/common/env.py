"""Environment configuration loading for local project execution."""

from pathlib import Path

from dotenv import load_dotenv


def load_project_env(project_root: Path) -> None:
    """Load project .env without overriding environment values set by the shell."""
    load_dotenv(dotenv_path=project_root / ".env", override=False)
