"""Run every external-validation document through the REAL production pipeline.

Pipeline (identical to /api/verify):
  file validation -> extraction -> 30-feature generation -> random_forest_v2 -> prediction

Records per-document prediction/risk/confidence/extracted fields/features,
computes overall + per-type metrics, performs error analysis and writes
monitoring/generalization_report.json.

VALIDATION ONLY: nothing is trained or written to models/.
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.ml import model as model_service  # noqa: E402
from app.services.extraction_service import extract_document  # noqa: E402
from app.services.feature_service import build_features_from_extraction  # noqa: E402
from app.utils.file_utils import validate_file  # noqa: E402
from src.features.build_features import FEATURE_COLUMNS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
VALIDATION_DIR = ROOT / "external_validation"
REPORT_PATH = ROOT / os.getenv("GENERALIZATION_REPORT", "monitoring/generalization_report.json")

CATEGORIES = ["academic", "completion", "training", "online", "technical", "workshop"]


def run_all():
    manifest = json.loads((VALIDATION_DIR / "manifest.json").read_text(encoding="utf-8"))
    _, features, metadata = model_service.load()
    print(f"Active model: {metadata['model_version']} | {len(features)} features")

    records = []
    for name, meta in manifest.items():
        path = VALIDATION_DIR / name
        content = path.read_bytes()
        try:
            ext = validate_file(path.name, content)
            extraction = extract_document(str(path), ext)
        except Exception as exc:  # noqa: BLE001
            records.append({
                "filename": name, "category": meta["category"],
                "expected": meta["expected"], "prediction": "error",
                "risk_score": None, "confidence": None,
                "extracted_fields": {}, "features": {}, "error": str(exc),
                "note": meta["note"], "source": meta["source"],
            })
            continue

        feats = build_features_from_extraction(extraction)
        result = model_service.predict(feats)
        records.append({
            "filename": name,
            "category": meta["category"],
            "expected": meta["expected"],
            "prediction": result["prediction"],
            "risk_score": result["risk_score"],
            "confidence": result["confidence"],
            "model_version": result["model_version"],
            "extracted_fields": {k: v for k, v in extraction.fields.items() if v},
            "text_preview": extraction.text[:250],
            "warnings": extraction.warnings,
            "features": feats,
            "note": meta["note"],
            "source": meta["source"],
        })

    return records, metadata


def analyze(records):
    valid = [r for r in records if r["prediction"] != "error"]
    correct = sum(1 for r in valid if r["prediction"] == r["expected"])
    accuracy = round(correct / len(valid), 4) if valid else 0.0

    gen = [r for r in valid if r["expected"] == "genuine"]
    sus = [r for r in valid if r["expected"] == "suspicious"]
    fp = [r for r in valid if r["expected"] == "genuine" and r["prediction"] == "suspicious"]
    fn = [r for r in valid if r["expected"] == "suspicious" and r["prediction"] == "genuine"]

    genuine_recall = round((len(gen) - len(fp)) / len(gen), 4) if gen else 0.0
    suspicious_recall = round((len(sus) - len(fn)) / len(sus), 4) if sus else 0.0
    fpr = round(len(fp) / len(gen), 4) if gen else 0.0
    fnr = round(len(fn) / len(sus), 4) if sus else 0.0

    per_type = {}
    for cat in CATEGORIES:
        c = [r for r in valid if r["category"] == cat]
        if not c:
            continue
        n_correct = sum(1 for r in c if r["prediction"] == r["expected"])
        g = [r for r in c if r["expected"] == "genuine"]
        s = [r for r in c if r["expected"] == "suspicious"]
        fp_c = [r for r in c if r["expected"] == "genuine" and r["prediction"] == "suspicious"]
        fn_c = [r for r in c if r["expected"] == "suspicious" and r["prediction"] == "genuine"]
        per_type[cat] = {
            "n": len(c),
            "accuracy": round(n_correct / len(c), 4),
            "genuine_recall": round((len(g) - len(fp_c)) / len(g), 4) if g else 0.0,
            "suspicious_recall": round((len(s) - len(fn_c)) / len(s), 4) if s else 0.0,
            "false_positives": [r["filename"] for r in fp_c],
            "false_negatives": [r["filename"] for r in fn_c],
        }

    return {
        "overall": {
            "n": len(valid), "accuracy": accuracy,
            "genuine_recall": genuine_recall, "suspicious_recall": suspicious_recall,
            "false_positive_rate": fpr, "false_negative_rate": fnr,
            "n_false_positives": len(fp), "n_false_negatives": len(fn),
            "false_positives": [r["filename"] for r in fp],
            "false_negatives": [r["filename"] for r in fn],
        },
        "per_type": per_type,
    }


def classify_error(r):
    """Best-effort cause classification: A extraction, B features, C coverage,
    D model, E ambiguous."""
    feats = r.get("features", {})
    if r["expected"] == "genuine" and r["prediction"] == "suspicious":
        if feats.get("completion_date_present", 0) == 0:
            return "A", "legit date format not recognized by DATE_RE (completion_date_present=0)"
        if feats.get("recipient_present", 0) == 0:
            return "A", "recipient phrase not covered by NAME_RE (recipient_present=0)"
        if feats.get("issuer_present", 0) == 0:
            return "A", "issuer not detected (no issuer marker / org keyword in text)"
        type_any = (feats.get("certificate_type_academic", 0)
                    or feats.get("certificate_type_completion", 0)
                    or feats.get("certificate_type_training", 0)
                    or feats.get("certificate_type_technical", 0))
        if not type_any:
            return "C", "document category has no certificate-type flag in feature schema"
        if feats.get("issuer_known", 0) == 0:
            return "C", "legit issuer not in KNOWN_ISSUERS (issuer_known=0)"
        if feats.get("grade_consistency_valid", 0) == 0 and feats.get("marks_pattern_valid", 0) == 1:
            return "E", "document is internally inconsistent (grade does not match marks); genuine label ambiguous"
        if feats.get("suspicious_keyword_count", 0) > 0 or feats.get("suspicious_url_present", 0) == 1:
            return "E", "doc contains suspicious markers but is expected genuine (ambiguous)"
        return "D", "complete structure and no fraud signal but scored suspicious (model limitation)"
    if r["expected"] == "suspicious" and r["prediction"] == "genuine":
        has_fraud_signal = (feats.get("suspicious_keyword_count", 0) > 0
                            or feats.get("suspicious_url_present", 0) == 1)
        if not has_fraud_signal:
            return "C", "fraud doc has no suspicious signal extracted; fraud not represented in features"
        return "E", "fraud signals present but weak vs. structure (ambiguous)"
    return "?", "unexpected"


def main():
    records, metadata = run_all()
    analysis = analyze(records)

    # error analysis
    errors = [r for r in records if r["prediction"] != "error" and r["prediction"] != r["expected"]]
    error_analysis = []
    for r in errors:
        cause, reason = classify_error(r)
        error_analysis.append({
            "filename": r["filename"], "category": r["category"],
            "expected": r["expected"], "prediction": r["prediction"],
            "risk_score": r["risk_score"],
            "extracted_fields": r["extracted_fields"],
            "features": r["features"],
            "likely_cause": cause,
            "reason": reason,
        })

    recommendations = [
        "COVERAGE (2 of 3 remaining FPs, technical/suleiman + technical/kim): genuine technical "
        "certificates produce certificate_type_academic/completion/training = 0, which is "
        "out-of-distribution for v2 (every genuine training row fires at least one type flag). "
        "Phase 5C should add technical/workshop certificate types (or fold them into "
        "completion/training) so the schema covers these categories.",
        "AMBIGUOUS (1 of 3, academic/deshpande): the document is internally inconsistent "
        "(grade B with 91/100 marks => grade_consistency_valid=0), an artifact of the external "
        "template hardcoding marks that do not match its grade. Not fixable without touching the "
        "frozen PDF; either regenerate the template with matching marks or accept the flag.",
        "RESOLVED in PHASE 5B (extraction + coverage): recipient phrases ('we thank', 'we are "
        "pleased to present'), dot/dash/slash date formats, marks-from-date bug (2025/05/19), "
        "'certified by'/'organized by'/labeled issuer fields, title-line issuer detection, "
        "'Awarded by the course faculty' false captures, academy->academic feature fix, expanded "
        "KNOWN_ISSUERS, and visual_blank_ratio train/runtime semantics alignment.",
        "RE-EVALUATE: after the Phase 5C dataset expansion and v3 retraining, re-run this exact "
        "frozen external set (unchanged) to measure genuine recall improvement before promoting.",
    ]

    report = {
        "model_version": metadata["model_version"],
        "feature_version": metadata["feature_schema_version"],
        "dataset_version": metadata["dataset_version"],
        "number_of_external_samples": len(records),
        "certificate_types": CATEGORIES,
        "overall_metrics": analysis["overall"],
        "per_type_metrics": analysis["per_type"],
        "false_positives": [r["filename"] for r in errors if r["expected"] == "genuine"],
        "false_negatives": [r["filename"] for r in errors if r["expected"] == "suspicious"],
        "error_analysis": error_analysis,
        "recommendations": recommendations,
        "records": [
            {k: r[k] for k in ("filename", "category", "expected", "prediction",
                               "risk_score", "confidence", "model_version",
                               "extracted_fields", "text_preview", "warnings",
                               "note", "source")}
            for r in records
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # console output
    print("\n=== EXTERNAL VALIDATION RESULTS ===")
    print(f"{'Category':<12}{'File':<42}{'Expected':<10}{'Predicted':<10}{'Risk':>8}{'Conf':>7}")
    for r in records:
        risk = "  -  " if r["risk_score"] is None else f"{r['risk_score']:.3f}"
        conf = "  -  " if r["confidence"] is None else f"{r['confidence']:.3f}"
        print(f"{r['category']:<12}{r['filename']:<42}{r['expected']:<10}{r['prediction']:<10}{risk:>8}{conf:>7}")

    o = analysis["overall"]
    print("\n=== OVERALL ===")
    print(f"accuracy={o['accuracy']} genuine_recall={o['genuine_recall']} "
          f"suspicious_recall={o['suspicious_recall']} FPR={o['false_positive_rate']} FNR={o['false_negative_rate']}")
    print("false_positives:", o["false_positives"])
    print("false_negatives:", o["false_negatives"])

    print("\n=== PER TYPE ===")
    for cat, m in analysis["per_type"].items():
        print(f"{cat:<12} n={m['n']} acc={m['accuracy']} gen_recall={m['genuine_recall']} "
              f"sus_recall={m['suspicious_recall']} FP={m['false_positives']} FN={m['false_negatives']}")

    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    main()