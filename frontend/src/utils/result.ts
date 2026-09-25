import type {
  DuplicateInfo,
  EvidenceDetails,
  ExplanationSignal,
  ExtractionInfo,
  Intelligence,
  IssuerVerification,
  OodStatus,
  RecommendedAction,
  ReviewPriority,
  ReviewStatus,
  VerificationDetail,
  VerificationEvidence,
  VerificationResponse,
} from "../types";

/**
 * Normalized result view shared by the verify workspace and the investigation
 * detail page. Both the live verification response and the persisted detail
 * endpoint expose these fields; the shape is normalized here so result
 * components never deal with union types.
 */
export interface ResultView {
  verificationId: string;
  filename: string | null;
  prediction: string;
  label: string | null;
  riskScore: number;
  confidence: number;
  modelVersion: string;
  createdAt: string | null;
  reviewStatus: ReviewStatus | null;
  issuer: string | null;
  certificateType: string | null;
  oodStatus: OodStatus | null;
  reviewPriority: ReviewPriority | null;
  message: string;
  recommendedAction?: RecommendedAction;
  warnings: string[];
  intelligence: Intelligence;
  positiveSignals: ExplanationSignal[];
  riskSignals: ExplanationSignal[];
  duplicate: DuplicateInfo;
  extraction?: ExtractionInfo;
  evidence?: VerificationEvidence;
  evidenceDetails?: EvidenceDetails;
  issuerVerification?: IssuerVerification;
}

type RawResult = VerificationResponse | VerificationDetail;

export function normalizeResult(data: RawResult): ResultView {
  const evidenceDetails = "evidence_details" in data ? data.evidence_details : undefined;
  return {
    verificationId: data.verification_id,
    filename: "filename" in data ? data.filename ?? null : null,
    prediction: data.prediction,
    label: "label" in data ? data.label ?? null : null,
    riskScore: data.risk_score,
    confidence: data.confidence,
    modelVersion: data.model_version,
    createdAt: data.created_at ?? null,
    reviewStatus: data.review_status ?? null,
    issuer: "issuer" in data ? data.issuer ?? null : null,
    certificateType:
      "certificate_type" in data && data.certificate_type
        ? typeof data.certificate_type === "string"
          ? data.certificate_type
          : JSON.stringify(data.certificate_type)
        : null,
    oodStatus: data.ood_status ?? null,
    reviewPriority: data.review_priority ?? null,
    message: "message" in data ? data.message : "",
    recommendedAction: "recommended_action" in data ? data.recommended_action : undefined,
    warnings: "warnings" in data ? data.warnings ?? [] : [],
    intelligence: data.intelligence ?? {},
    positiveSignals: data.positive_signals ?? [],
    riskSignals: data.risk_signals ?? [],
    duplicate: data.duplicate ?? {
      is_duplicate: false,
      duplicate_of: null,
      duplicate_type: null,
    },
    extraction: data.extraction && Object.keys(data.extraction).length ? data.extraction : undefined,
    evidence: data.verification_evidence && Object.keys(data.verification_evidence).length
      ? data.verification_evidence
      : undefined,
    evidenceDetails,
    issuerVerification:
      evidenceDetails?.issuer_verification ?? data.issuer_verification ?? undefined,
  };
}

/** True when an evidence block carries at least the assessment field. */
export function hasEvidence(data: ResultView): boolean {
  return Boolean(data.evidence?.assessment);
}