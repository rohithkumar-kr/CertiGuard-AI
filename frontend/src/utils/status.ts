import type {
  FinalAssessment,
  Prediction,
  ReviewStatus,
  VerificationEvidence,
} from "../types";

/**
 * Case-level statuses used throughout the platform. Derived strictly from
 * backend-provided values (review status for records, final assessment for
 * evidence blocks); nothing is invented.
 */
export type CaseStatus =
  | "verified"
  | "requires_verification"
  | "suspicious"
  | "insufficient_evidence"
  | "error";

export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  verified: "Verified",
  requires_verification: "Requires Verification",
  suspicious: "Suspicious",
  insufficient_evidence: "Insufficient Evidence",
  error: "Error",
};

export const ASSESSMENT_LABELS: Record<string, string> = {
  LIKELY_GENUINE: "Verified",
  LIKELY_SUSPICIOUS: "Suspicious",
  REQUIRES_VERIFICATION: "Requires Verification",
  INSUFFICIENT_EVIDENCE: "Insufficient Evidence",
};

export const ASSESSMENT_STATUS: Record<FinalAssessment, CaseStatus> = {
  LIKELY_GENUINE: "verified",
  LIKELY_SUSPICIOUS: "suspicious",
  REQUIRES_VERIFICATION: "requires_verification",
  INSUFFICIENT_EVIDENCE: "insufficient_evidence",
};

export function reviewStatusToCaseStatus(
  status: ReviewStatus | null | undefined,
): CaseStatus | null {
  switch (status) {
    case "low_risk":
      return "verified";
    case "manual_review":
      return "requires_verification";
    case "high_risk":
      return "suspicious";
    default:
      return null;
  }
}

export function assessmentToCaseStatus(
  assessment: string | undefined | null,
): CaseStatus | null {
  if (!assessment) return null;
  const mapped = ASSESSMENT_STATUS[assessment as FinalAssessment];
  return mapped ?? null;
}

export function evidenceToCaseStatus(
  evidence: VerificationEvidence | undefined | null,
): CaseStatus | null {
  if (!evidence) return null;
  return assessmentToCaseStatus(evidence.assessment);
}

export function predictionToCaseStatus(
  prediction: Prediction | string | null | undefined,
): CaseStatus | null {
  if (prediction === "genuine") return "verified";
  if (prediction === "suspicious") return "suspicious";
  if (prediction === "error") return "error";
  return null;
}

export const PREDICTION_LABELS: Record<string, string> = {
  genuine: "Genuine",
  suspicious: "Suspicious",
  error: "Error",
};

export const REVIEW_LABELS: Record<string, string> = {
  low_risk: "Low risk",
  manual_review: "Manual review",
  high_risk: "High risk",
};

export const CERT_TYPE_LABELS: Record<string, string> = {
  academic: "Academic",
  completion: "Completion",
  training: "Training",
  online: "Online",
  technical: "Technical",
  workshop: "Workshop",
};

export const OOD_LABELS: Record<string, string> = {
  normal: "Normal",
  unusual: "Unusual",
  insufficient_information: "Insufficient info",
};

export const PRIORITY_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

export const EVIDENCE_STATUS_LABELS: Record<string, string> = {
  PASS: "Pass",
  WARNING: "Warning",
  FAIL: "Fail",
  UNKNOWN: "Unknown",
};

export const EVIDENCE_CATEGORY_LABELS: Record<string, string> = {
  ML: "ML Classification",
  EXTRACTION: "Document Extraction",
  STRUCTURE: "Document Structure",
  SEMANTICS: "Semantic Analysis",
  CONSISTENCY: "Identity Consistency",
  VISUAL: "Visual Analysis",
  TAMPERING: "Tampering Analysis",
  QR: "QR / Verification Code",
  ISSUER: "Issuer Verification",
  ANOMALY: "Anomaly Detection",
  DUPLICATE: "Duplicate Detection",
  EXTERNAL: "External Verification",
  FORENSICS: "Document Forensics",
};

export const SEVERITY_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export function evidenceCategoryLabel(category: string): string {
  return EVIDENCE_CATEGORY_LABELS[category] ?? category;
}