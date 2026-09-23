import type { EvidenceDetails } from "../../types";
import type { ResultView } from "../../utils/result";
import { KeyValue, KeyValueGrid, EvidenceStatusChip } from "../ui/DataDisplay";

const STATUS_META: Record<
  string,
  { label: string; chip: "PASS" | "WARNING" | "FAIL" | "UNKNOWN"; icon: string }
> = {
  VERIFIED_BY_ISSUER: { label: "Issuer verified", chip: "PASS", icon: "\u2713" },
  NOT_VERIFIED: { label: "Issuer could not be verified", chip: "FAIL", icon: "\u26a0" },
  VERIFICATION_UNAVAILABLE: { label: "Verification unavailable", chip: "WARNING", icon: "?" },
  ISSUER_UNKNOWN: { label: "Unknown issuer", chip: "WARNING", icon: "?" },
};

export function IssuerPanel({ result }: { result: ResultView }) {
  const issuer: NonNullable<EvidenceDetails["issuer"]> =
    result.evidenceDetails?.issuer ?? { status: "" };
  const evidenceItems = result.evidence?.evidence_items ?? [];
  const issuerItems = evidenceItems.filter((it) => it.category === "ISSUER");
  const iv = result.issuerVerification;

  const statusStr = issuer.status ? String(issuer.status) : "";
  const legacyStatusLabel =
    statusStr.includes("verified") || statusStr.includes("known")
      ? "Issuer recognized"
      : statusStr.includes("block")
        ? "Issuer blocked"
        : statusStr.includes("mismatch")
          ? "Domain mismatch"
          : statusStr === "no_qr" || statusStr.includes("unknown")
            ? "Not in registry"
            : statusStr || "Not available";

  const meta = iv?.status ? STATUS_META[iv.status] : undefined;
  const panelLabel = meta?.label ?? legacyStatusLabel;
  const panelChip: "PASS" | "WARNING" | "FAIL" | "UNKNOWN" =
    meta?.chip ??
    (statusStr.includes("verified") || statusStr.includes("known")
      ? "PASS"
      : statusStr.includes("block")
        ? "FAIL"
        : statusStr.includes("mismatch")
          ? "WARNING"
          : "WARNING");

  const identifierNote =
    iv?.checked_identifiers && iv.checked_identifiers.length > 0
      ? "Credential identifiers detected"
      : null;

  const unavailableAction =
    iv?.status === "VERIFICATION_UNAVAILABLE"
      ? "Recommended action: verify using the issuer's official verification service."
      : null;

  return (
    <div>
      <div className="card">
        <div className="card__head">
          <h2>
            {meta?.icon ? <span aria-hidden="true">{meta.icon} </span> : null}
            Issuer verification
          </h2>
          {iv?.status || issuer.status ? <EvidenceStatusChip status={panelChip} /> : null}
        </div>
        <KeyValueGrid>
          <KeyValue label="Status" value={panelLabel} />
          <KeyValue
            label="Extracted issuer"
            value={iv?.issuer ?? issuer.issuer_name ?? result.issuer ?? "Not available"}
            muted={!iv?.issuer && !issuer.issuer_name && !result.issuer}
          />
          {iv ? (
            <>
              <KeyValue
                label="Verification method"
                value={iv.verification_method ? String(iv.verification_method) : "Not applicable"}
                muted={!iv.verification_method}
              />
              <KeyValue
                label="Checked identifiers"
                value={
                  iv.checked_identifiers && iv.checked_identifiers.length > 0
                    ? iv.checked_identifiers.join(", ")
                    : "None"
                }
                muted={!iv.checked_identifiers || iv.checked_identifiers.length === 0}
              />
              {iv.verification_url ? (
                <KeyValue label="Verification URL" value={iv.verification_url} />
              ) : null}
            </>
          ) : (
            <>
              <KeyValue
                label="Domain consistency"
                value={
                  issuer.domain_consistency
                    ? String(issuer.domain_consistency).replace(/_/g, " ")
                    : "Not available"
                }
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
          )}
        </KeyValueGrid>

        {(iv?.reason || identifierNote || unavailableAction) ||
        (issuer.notes && issuer.notes.length > 0) ? (
          <ul className="group-list" style={{ marginTop: 14 }}>
            {identifierNote ? (
              <li
                key="idnote"
                className="group-list__item"
                style={{ fontSize: 12.5, color: "var(--text-secondary)" }}
              >
                {identifierNote}
              </li>
            ) : null}
            {iv?.reason ? (
              <li
                key="reason"
                className="group-list__item"
                style={{ fontSize: 12.5, color: "var(--text-secondary)" }}
              >
                {iv.reason}
              </li>
            ) : null}
            {unavailableAction ? (
              <li
                key="action"
                className="group-list__item"
                style={{ fontSize: 12.5, color: "var(--text-secondary)" }}
              >
                {unavailableAction}
              </li>
            ) : null}
            {!iv &&
              issuer.notes &&
              issuer.notes.map((note) => (
                <li
                  key={note}
                  className="group-list__item"
                  style={{ fontSize: 12.5, color: "var(--text-secondary)" }}
                >
                  {note}
                </li>
              ))}
          </ul>
        ) : null}
      </div>

      {issuerItems.length > 0 ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card__head">
            <h2>Issuer evidence findings</h2>
          </div>
          <ul className="group-list">
            {issuerItems.map((it, idx) => (
              <li key={`${it.signal}-${idx}`} className="group-list__item">
                <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <EvidenceStatusChip status={it.status} />
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                      {it.signal}
                    </div>
                    <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>
                      {it.explanation}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="muted" style={{ fontSize: 12, marginTop: 14 }}>
        An unavailable or unknown issuer is not treated as fraud. The platform
        only flags issuers whose own verification service returned a definitive
        negative, or explicit domain conflicts.
      </p>
    </div>
  );
}