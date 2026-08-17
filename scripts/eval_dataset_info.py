"""Print metadata for the versioned L1 evaluation dataset.

This developer utility does not run a model. It derives its output directly from
``data/eval_cases.json`` for use in documentation, experiment notes, and CI.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).parents[1]
EVAL_CASES_PATH = ROOT / "data" / "eval_cases.json"


def summarize_eval_cases(path: Path = EVAL_CASES_PATH) -> dict[str, object]:
    """Return reproducibility metadata for a valid eval-cases JSON list."""
    raw = path.read_bytes()
    cases = json.loads(raw)
    if not isinstance(cases, list):
        raise ValueError(f"评估集必须是 JSON array: {path}")

    buckets = Counter(
        str(case.get("bucket", "unknown"))
        for case in cases
        if isinstance(case, dict)
    )
    return {
        "dataset": str(path.relative_to(ROOT)),
        "case_count": len(cases),
        "bucket_count": len(buckets),
        "buckets": dict(sorted(buckets.items())),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def main() -> None:
    print(json.dumps(summarize_eval_cases(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
