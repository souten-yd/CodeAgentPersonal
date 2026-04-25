from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import tempfile
import zipfile

from app.nexus.evidence import list_evidence_items
from app.nexus.jobs import get_job


_BUNDLE_DIR = Path(tempfile.gettempdir()) / "codeagent_nexus_bundles"
_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)



def create_nexus_bundle(job_id: str, report: dict) -> Path:
    """Create nexus_bundle_{job_id}.zip with evidence/report/job artifacts."""
    if not job_id:
        raise ValueError("job_id is required")

    job = get_job(job_id)
    if not job:
        raise ValueError("job not found")

    evidence = list_evidence_items(job_id)
    report_md = Path(report["report_md_path"])
    report_html = Path(report["report_html_path"])

    zip_path = _BUNDLE_DIR / f"nexus_bundle_{job_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("evidence.json", json.dumps(evidence, ensure_ascii=False, indent=2))

        csv_buf = io.StringIO()
        writer = csv.DictWriter(csv_buf, fieldnames=["citation_label", "source_url", "retrieved_at", "chunk_id"])
        writer.writeheader()
        for item in evidence:
            writer.writerow(
                {
                    "citation_label": item.get("citation_label", ""),
                    "source_url": item.get("source_url", ""),
                    "retrieved_at": item.get("retrieved_at", ""),
                    "chunk_id": item.get("chunk_id", ""),
                }
            )
        zf.writestr("sources.csv", csv_buf.getvalue())

        if report_md.exists():
            zf.write(report_md, "report.md")
        if report_html.exists():
            zf.write(report_html, "report.html")

        zf.writestr("job.json", json.dumps(job, ensure_ascii=False, indent=2))

    return zip_path
