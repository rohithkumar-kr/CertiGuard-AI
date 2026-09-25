import type { EvidenceDetails } from "../../types";
import type { ResultView } from "../../utils/result";
import { EvidenceStatusChip, KeyValue, KeyValueGrid } from "../ui/DataDisplay";

const STATUS_META: Record<
  string,
  { label: string; chip: "PASS" | "WARNING" | "FAIL" | "UNKNOWN" }
> = {
  VERIFIED_BY_ISSUER: { label: "Issuer verified", chip: "PASS" },
  NOT_VERIFIED: { label: "Issuer could not be verified", chip: "FAIL" },
  VERIFICATION_UNAVAILABLE: { label: "Verification unavailable", chip: "WARNING" },
  ISSUER_UNKNOWN: { label: "Unknown issuer", chip: "WARNING" },
};

const LEGACY_STATUS_META: Record<
  string,
  { label: string; chip: "PASS" | "WARNING" | "FAIL" | "UNKNOWN" }
> = {
  unknown: { label: "Unknown issuer", chip: "WARNING" },
  externally_verified: { label: "Issuer externally verified", chip: "PASS" },
  known_verified: { label: "Issuer recognized", chip: "PASS" },
  known_unverified: { label: "Issuer not verified", chip: "WARNING" },
  domain_verified: { label: "Issuer domain verified", chip: "PASS" },
  extracted_but_unverified: { label: "Issuer extracted but not verified", chip: "WARNING" },
};

function textValue(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

export function IssuerPanel({ result }: { result: ResultView }) {
  const issuerDetails = result.evidenceDetails?.issuer;
  const issuer: NonNullable<EvidenceDetails["issuer"]> =
    issuerDetails && Object.keys(issuerDetails).length > 0
      ? issuerDetails
      : { status: "" };
  const verification = result.issuerVerification;
  const iv =
    verification && typeof verification === "object" && Object.keys(verification).length > 0
      ? verification
      : undefined;
  const evidenceItems = result.evidence?.evidence_items ?? [];
  const issuerItems = evidenceItems.filter((item) => item.category === "ISSUER");
  const statusValue = typeof issuer.status === "string" ? issuer.status : "";
  const legacyMeta = LEGACY_STATUS_META[statusValue];
  const statusMeta = iv?.status ? STATUS_META[iv.status] : undefined;
  const statusLabel = statusMeta?.label ?? legacyMeta?.label ?? (statusValue || "Not available");
  const statusChip = statusMeta?.chip ?? legacyMeta?.chip ?? "UNKNOWN";
  const issuerName =
    textValue(iv?.issuer) ??
    textValue(issuer.issuer_name) ??
    textValue(result.issuer);
  const checkedIdentifiers = Array.isArray(iv?.checked_identifiers)
    ? iv.checked_identifiers.map((value) => textValue(value)).filter((value): value is string => Boolean(value))
    : [];
  const explanation = textValue(iv?.reason) ?? textValue(iv?.error_reason);
  const verificationMethod = textValue(iv?.verification_method);
  const verificationUrl = textValue(iv?.verification_url);
  const notes = Array.isArray(issuer.notes)
    ? issuer.notes.map((note) => textValue(note)).filter((note): note is string => Boolean(note))
    : [];

  return (
    <div className="issuer-panel">
      <div className="card">
        <div className="card__head">
          <div>
            <h2>Issuer verification</h2>
            <p className="card__head-sub">Registry and issuer-service checks</p>
          </div>
          <EvidenceStatusChip status={statusChip} />
        </div>
        <KeyValueGrid>
          <KeyValue
            label="Status"
            value={statusLabel || "Not available"}
            muted={!statusMeta && !legacyMeta && !statusValue}
          />
          <KeyValue
            label="Extracted issuer"
            value={issuerName ?? "Not available"}
            muted={!issuerName}
          />
          <KeyValue
            label="Verification method"
            value={verificationMethod ?? (iv ? "Not applicable" : "Not available")}
            muted={!verificationMethod}
          />
          <KeyValue
            label="Checked identifiers"
            value={checkedIdentifiers.length > 0 ? checkedIdentifiers.join(", ") : "None"}
            muted={checkedIdentifiers.length === 0}
          />
          {verificationUrl ? (
            <KeyValue label="Verification URL" value={verificationUrl} mono />
          ) : null}
          {!iv ? (
            <>
              <KeyValue
                label="Domain consistency"
                value={textValue(issuer.domain_consistency) ?? "Not available"}
                muted={!issuer.domain_consistency}
              />
              <KeyValue
                label="QR domains"
                value={
                  Array.isArray(issuer.qr_domains) && issuer.qr_domains.length > 0
                    ? issuer.qr_domains.join(", ")
                    : "None detected"
                }
                muted
              />
              <KeyValue
                label="Candidate domains"
                value={
                  Array.isArray(issuer.candidate_domains) && issuer.candidate_domains.length > 0
                    ? issuer.candidate_domains.join(", ")
                    : "None"
                }
                muted
              />
            </>
          ) : null}
        </KeyValueGrid>

        <div className="issuer-explanation">
          <h3>Explanation</h3>
          <p>
            {explanation ??
              "No issuer explanation was returned for this verification."}
          </p>
        </div>
        {notes.length > 0 ? (
          <ul className="report-note-list">
            {notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        ) : null}
        <p className="report-note">
          An unavailable or unknown issuer is not treated as fraud. The
          platform only flags issuers whose own verification service returned a
          definitive negative, or explicit domain conflicts.
        </p>
      </div>

      {issuerItems.length > 0 ? (
        <div className="card issuer-findings">
          <div className="card__head">
            <div>
              <h2>Issuer evidence findings</h2>
              <p className="card__head-sub">Signals returned for issuer verification</p>
            </div>
            <span className="card__head-sub">{issuerItems.length} recorded</span>
          </div>
          <ol className="evidence-timeline evidence-timeline--report">
            {issuerItems.map((item, index) => (
              <li className="evidence-timeline__item" key={`${item.signal}-${index}`}>
                <span
                  className={`evidence-timeline__dot evidence-timeline__dot--${item.status.toLowerCase()}`}
                  aria-hidden="true"
                />
                <div className="evidence-timeline__head">
                  <EvidenceStatusChip status={item.status} />
                  <span className="evidence-timeline__signal">{item.signal}</span>
                </div>
                <p className="evidence-timeline__detail">
                  {item.explanation || "No description was returned for this finding."}
                </p>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  );
}
