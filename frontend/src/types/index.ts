export type Prediction = "genuine" | "suspicious";
export type ReviewStatus = "low_risk" | "manual_review" | "high_risk";
export type OodStatus = "normal" | "unusual" | "insufficient_information";
export type ReviewPriority = "low" | "medium" | "high";
export type ReviewerLabel = "confirmed_genuine" | "confirmed_suspicious" | "uncertain";

export interface HealthResponse {
  status: string;
  app: string;
  model_version: string | null;
  model_loaded: boolean;
}

export interface CertificateTypeFlags {
  academic: number;
  completion: number;
  training: number;
  technical: number;
}

export interface ExplanationSignal {
  key: string;
  label: string;
  status: "ok" | "attention";
  severity?: "low" | "medium" | "high";
  detail: string;
}

export interface IdentityField {
  label: string;
  value: string | number | null;
  present: boolean;
}

export interface CertificateTypeInfo {
  flags: Record<string, number>;
  primary: string;
}

export interface ExtractionInfo {
  method: "pdf_text" | "ocr" | "hybrid" | "none" | string;
  confidence: number | null;
  confidence_level: "high" | "medium" | "low" | string;
  text_length: number;
  completeness: number;
  ocr_used: boolean;
  ocr_failed: boolean;
  ocr_pages: number;
  fields_detected: number;
  fields_total: number;
}

export interface Intelligence {
  certificate_type: CertificateTypeInfo;
  identity: Record<string, IdentityField>;
  structural_signals: Record<string, { label: string; present: boolean }>;
  quality_indicators: {
    blank_document: boolean;
    text_extraction_quality: string;
    text_present: boolean;
    visual_quality: string;
    noise: number;
    sharpness: number;
    blank_ratio: number;
    color_anomaly: boolean;
    extraction_method?: string;
    extraction_confidence?: number | null;
    ocr_used?: boolean;
    ocr_failed?: boolean;
    processing_warnings: string[];
  };
  consistency_findings: {
    key: string;
    label: string;
    status: string;
    severity: string;
    detail: string;
  }[];
  structure_completeness: number;
}

export interface RecommendedAction {
  action: string;
  heading: string;
  message: string;
}

export type FinalAssessment =
  | "LIKELY_GENUINE"
  | "LIKELY_SUSPICIOUS"
  | "REQUIRES_VERIFICATION"
  | "INSUFFICIENT_EVIDENCE";

export interface EvidenceItem {
  source: string;
  category: string;
  signal: string;
  severity: "low" | "medium" | "high";
  confidence: number;
  explanation: string;
  status: "PASS" | "WARNING" | "FAIL" | "UNKNOWN";
}

export type IssuerVerificationStatus =
  | "VERIFIED_BY_ISSUER"
  | "NOT_VERIFIED"
  | "VERIFICATION_UNAVAILABLE"
  | "ISSUER_UNKNOWN";

export interface IssuerVerification {
  status: IssuerVerificationStatus | string;
  issuer?: string | null;
  verification_method?: string | null;
  verification_url?: string | null;
  checked_identifiers?: string[];
  source?: string;
  reason?: string;
  confidence?: number;
  timestamp?: string | null;
  error_reason?: string | null;
}

export interface VerificationEvidence {
  assessment: FinalAssessment;
  confidence: number;
  recommended_action: string;
  category_status: Record<string, string>;
  summary: {
    positive_mass?: number;
    negative_mass?: number;
    uncertainty_count?: number;
    ml_suspicious?: boolean;
    strong_tampering?: boolean;
    externally_verified?: boolean;
    ood_status?: string;
    anomaly_level?: string;
    anomaly_score?: number;
    duplicate?: boolean;
  };
  evidence_items: EvidenceItem[];
}

export interface EvidenceDetails {
  forensics?: Record<string, unknown>;
  forensic_anomalies?: { key: string; label: string; severity: string; detail: string }[];
  visual?: Record<string, unknown>;
  tampering?: { status: string; findings: unknown[]; signals?: Record<string, unknown> };
  qr?: { status: string; count: number; codes: string[]; invalid_qr?: boolean; notes?: string[] };
  issuer?: {
    status: string;
    issuer_name?: string | null;
    domain_consistency?: string | null;
    qr_domains?: string[];
    candidate_domains?: string[];
    external?: unknown;
    notes?: string[];
  };
  issuer_verification?: IssuerVerification;
  semantics?: {
    credential_statement_present?: boolean;
    roles?: Record<string, boolean>;
    credential_level?: string;
    verification_present?: boolean;
  };
  anomaly?: { score?: number; level?: string; contributors?: unknown[] };
}

export interface DuplicateInfo {
  is_duplicate: boolean;
  duplicate_of: string | null;
  duplicate_type: "file" | "cert_id" | "identity" | null;
}

export interface VerificationResponse {
  verification_id: string;
  prediction: Prediction;
  label: string;
  risk_score: number;
  confidence: number;
  message: string;
  model_version: string;
  certificate_type?: CertificateTypeFlags;
  explanation?: ExplanationSignal[];
  extracted: Record<string, string | number | null>;
  warnings: string[];
  created_at: string | null;
  review_status: ReviewStatus;
  recommended_action: RecommendedAction;
  intelligence: Intelligence;
  positive_signals: ExplanationSignal[];
  risk_signals: ExplanationSignal[];
  duplicate: DuplicateInfo;
  ood_status?: OodStatus;
  review_priority?: ReviewPriority;
  extraction_completeness?: number;
  extraction?: ExtractionInfo;
  verification_evidence?: VerificationEvidence;
  issuer_verification?: IssuerVerification;
}

export interface VerificationRecord {
  verification_id: string;
  filename: string | null;
  prediction: string;
  risk_score: number;
  confidence: number;
  model_version: string;
  created_at: string | null;
  review_status: ReviewStatus | null;
  issuer: string | null;
  certificate_type: string | null;
  duplicate_of: string | null;
  duplicate_type: string | null;
  ood_status?: OodStatus | null;
  review_priority?: ReviewPriority | null;
  reviewer_label?: ReviewerLabel | null;
  reviewed_at?: string | null;
  is_disagreement?: boolean | null;
}

export interface VerificationDetail {
  verification_id: string;
  filename: string | null;
  prediction: string;
  label: string | null;
  risk_score: number;
  confidence: number;
  model_version: string;
  created_at: string | null;
  error: string | null;
  review_status: ReviewStatus | null;
  issuer: string | null;
  certificate_type: string | null;
  extracted_info: string | null;
  duplicate_of: string | null;
  duplicate_type: string | null;
  ood_status: OodStatus | null;
  review_priority: ReviewPriority | null;
  intelligence: Intelligence;
  positive_signals: ExplanationSignal[];
  risk_signals: ExplanationSignal[];
  duplicate: DuplicateInfo;
  extraction?: ExtractionInfo;
  reviewer_label?: ReviewerLabel | null;
  reviewer_note?: string | null;
  reviewed_at?: string | null;
  is_disagreement?: boolean | null;
  verification_evidence?: VerificationEvidence;
  evidence_details?: EvidenceDetails;
  issuer_verification?: IssuerVerification;
}

export interface FeedbackSummary {
  total_reviewed: number;
  not_reviewed: number;
  confirmed_genuine: number;
  confirmed_suspicious: number;
  uncertain: number;
  decisive_reviews: number;
  agreement_count: number;
  disagreement_count: number;
  agreement_rate: number | null;
  disagreement_rate: number | null;
}

export interface FeedbackRecord {
  verification_id: string;
  reviewer_label: ReviewerLabel;
  reviewer_note: string | null;
  reviewed_at: string | null;
  original_prediction: string;
  original_risk_score: number;
  model_version: string | null;
  certificate_type: string | null;
  extraction_completeness: number | null;
  review_status: ReviewStatus | null;
  ood_status: OodStatus | null;
  review_priority: ReviewPriority | null;
  is_disagreement: boolean | null;
  split: string | null;
  dataset_batch: string | null;
}

export interface FeedbackAnalytics {
  summary: FeedbackSummary;
  overall: Record<string, unknown>;
  by_certificate_type: Record<string, unknown>;
  by_issuer: Record<string, unknown>;
  by_review_status: Record<string, unknown>;
  by_priority: Record<string, unknown>;
  by_extraction_completeness: Record<string, unknown>;
  average_extraction_completeness: number | null;
  ood_distribution: Record<string, number>;
  review_priority_distribution: Record<string, number>;
  manual_review_rate: number | null;
  minimum_metric_samples: number;
}

export interface VerificationSummary {
  total: number;
  genuine_count: number;
  suspicious_count: number;
  manual_review_count: number;
  average_risk_score: number;
}

export interface AuditEvent {
  id: number;
  verification_id: string;
  event_type: string;
  stage: string | null;
  status: string;
  severity: "success" | "info" | "warning" | "error" | "unknown" | string;
  title: string;
  description: string | null;
  details: Record<string, unknown>;
  created_at: string | null;
}

export interface AuditTrailResponse {
  verification_id: string;
  events: AuditEvent[];
}

export interface MetricsResponse {
  total_verifications: number;
  genuine_count: number;
  suspicious_count: number;
  error_count: number;
  prediction_distribution: Record<string, number>;
  certificate_type_distribution: Record<string, number>;
  average_risk_score: number;
  average_confidence: number;
  model_versions: Record<string, number>;
  recent: VerificationRecord[];
  review_status_distribution: Record<string, number>;
  average_extraction_completeness: number;
  issuer_distribution: Record<string, number>;
  manual_review_rate: number;
}

export interface ModelInfoResponse {
  model_version: string;
  model_name: string;
  features: string[];
  metrics: Record<string, number | number[][]>;
  created_at: string | null;
}