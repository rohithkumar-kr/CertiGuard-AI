"""Phase 12 validation run (M13).

Verifies the external-validation corpus + the known-difficult regression set
through the FULL pipeline (including the evidence engine), records reviewer
ground truth from the manifest, and produces the Phase 12 evaluation report
(confusion matrix, FPR/FNR, breakdowns, FP/FN lists).

Uses a dedicated validation database so it never pollutes the development DB.

Usage:
    python scripts/run_phase12_validation.py
    python scripts/run_phase12_validation.py --output monitoring/phase12_report.json
"""

import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="phase12_validation_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'validation.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")

from app.database.database import SessionLocal, init_db  # noqa: E402
from app.services.verification_service import verify_document  # noqa: E402
from app.services.feedback_service import record_feedback  # noqa: E402
from scripts.generate_phase12_report import generate_report  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXTERNAL = ROOT / "external_validation"

KNOWN_DIFFICULT = [
    (ROOT / "uploads" / "7db3d8127651442888419df4aa6567da.pdf", "genuine", "Introduction to Modern AI (image-only)"),
    (ROOT / "uploads" / "2c857804dcbd498bb83e5517815ed206.pdf", "genuine", "CCNA (generic course phrase)"),
    (ROOT / "tests" / "fixtures" / "python_essentials.pdf", "genuine", "Python Essentials 1 (issuer clause)"),
]


def _load_manifest():
    with open(EXTERNAL / "manifest.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    output = ROOT / "monitoring" / "phase12_report.json"
    if len(sys.argv) > 1 and sys.argv[1].startswith("--output="):
        output = ROOT / sys.argv[1].split("=", 1)[1]

    init_db()
    db = SessionLocal()
    results = []

    try:
        # --- external validation corpus ---
        manifest = _load_manifest()
        for rel, meta in manifest.items():
            path = EXTERNAL / rel
            if not path.exists():
                print(f"skip (missing): {rel}")
                continue
            expected = meta["expected"]
            body = verify_document(rel, path.read_bytes(), db)
            pred = body["prediction"]
            assessment = body["verification_evidence"]["assessment"]
            results.append({
                "document": rel, "category": meta["category"],
                "expected": expected, "prediction": pred,
                "risk": round(body["risk_score"], 4),
                "assessment": assessment, "source": meta["source"],
            })
            ok = (expected == "genuine") == (pred == "genuine")
            print(f"{'OK ' if ok else 'DIFF'} {rel:45s} expected={expected:9s} "
                  f"prediction={pred:9s} risk={body['risk_score']:.3f} "
                  f"assessment={assessment:20s}")
            if pred != "error":
                record_feedback(db, body["verification_id"],
                                "confirmed_genuine" if expected == "genuine" else "confirmed_suspicious",
                                reviewer_note=f"Phase 12 validation: {meta['note']}")

        # --- known-difficult regression set ---
        for path, expected, label in KNOWN_DIFFICULT:
            if not path.exists():
                print(f"skip (missing): {path.name}")
                continue
            body = verify_document(path.name, path.read_bytes(), db)
            pred = body["prediction"]
            assessment = body["verification_evidence"]["assessment"]
            results.append({
                "document": path.name, "category": "regression",
                "expected": expected, "prediction": pred,
                "risk": round(body["risk_score"], 4),
                "assessment": assessment, "source": "known-difficult",
            })
            ok = (expected == "genuine") == (pred == "genuine")
            print(f"{'OK ' if ok else 'DIFF'} {path.name:45s} expected={expected:9s} "
                  f"prediction={pred:9s} risk={body['risk_score']:.3f} "
                  f"assessment={assessment:20s}")
            if pred != "error":
                record_feedback(db, body["verification_id"],
                                "confirmed_genuine" if expected == "genuine" else "confirmed_suspicious",
                                reviewer_note=f"Phase 12 validation: {label}")

        report = generate_report(db)
        report["per_document"] = results
    finally:
        db.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    ee = report["evidence_engine"]
    ml = report["ml_model"]
    print("\n=== Phase 12 validation summary ===")
    print(f"Documents verified: {len(results)}")
    print(f"ML model:        {ml}")
    print(f"Evidence engine: {ee}")
    print(f"FPs: {len(report['false_positives'])}  FNs: {len(report['false_negatives'])}")
    print(f"\nReport written to {output}")


if __name__ == "__main__":
    main()