"""Execute the plain-Python notebook cells without adding notebook dependencies.

Outputs stay in stdout; committed notebooks remain clean, without embedded data.
"""

import json
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    paths = sys.argv[1:] or [
        "notebooks/01_silver_exploration.ipynb",
        "notebooks/02_silver_contract_tests.ipynb",
    ]
    for relative in paths:
        path = root / relative
        notebook = json.loads(path.read_text())
        namespace = {"__name__": "__main__"}
        try:
            for index, cell in enumerate(notebook["cells"]):
                if cell["cell_type"] == "code":
                    print(f"Executing {path.name} cell {index}", flush=True)
                    exec(  # noqa: S102 - executes explicitly selected project notebooks
                        compile(
                            "".join(cell["source"]), f"{path.name}:cell{index}", "exec"
                        ),
                        namespace,
                    )
        finally:
            if "spark" in namespace:
                namespace["spark"].stop()
            if "workspace" in namespace:
                namespace["workspace"].cleanup()
        print(f"Validated {relative}", flush=True)


if __name__ == "__main__":
    main()
