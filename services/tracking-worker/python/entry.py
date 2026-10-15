"""Absolute release entry, independent of the job cwd or editable development installs."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tracking.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
