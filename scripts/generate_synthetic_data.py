from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qualitytrace.data_factory import generate_dataset, validate_persisted_dataset  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="生成或核验 QualityTrace 8D 的确定性合成数据")
    parser.add_argument("--check", action="store_true", help="只核验当前数据，不改文件")
    args = parser.parse_args()
    result = validate_persisted_dataset(ROOT) if args.check else generate_dataset(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.check and not result["valid"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
