"""Generate the PIR-0 Project Intelligence consumer inventory artifact."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.project_intelligence.inspection.consumer_inventory import write_inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/generated/atlas_project_intelligence_consumer_inventory.json"),
    )
    args = parser.parse_args()
    inventory = write_inventory(args.root, args.output)
    summary = inventory["summary"]
    print(
        "wrote {output} "
        "production_entrypoints={production_entrypoint_count} "
        "legacy_consumers={legacy_production_consumer_count} "
        "facades={facade_module_count} "
        "adapters={adapter_module_count} "
        "critical_findings={critical_finding_count}".format(output=args.output.as_posix(), **summary)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
