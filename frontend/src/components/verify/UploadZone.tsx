import { useCallback, useRef, useState } from "react";
import { formatBytes, formatFileType } from "../../utils/format";

const ALLOWED_EXTENSIONS = ["pdf", "jpg", "jpeg", "png"];
const MAX_SIZE_BYTES = 10 * 1024 * 1024;

export function describeFileProblem(file: File): string | null {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `Unsupported file type ".${ext}". Please upload a PDF, JPG, JPEG, or PNG certificate.`;
  }
  if (file.size > MAX_SIZE_BYTES) {
    return `File is too large (${formatBytes(file.size)}). Maximum allowed size is 10 MB.`;
  }
  if (file.size === 0) {
    return "The selected file is empty.";
  }
  return null;
}

interface UploadZoneProps {
  file: File | null;
  loading: boolean;
  onFileChange: (file: File | null) => void;
  onVerify: () => void;
  error?: string | null;
}

export function UploadZone({ file, loading, onFileChange, onVerify, error }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const acceptFile = useCallback(
    (candidate: File | null) => {
      onFileChange(candidate);
    },
    [onFileChange],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const dropped = e.dataTransfer.files?.[0] ?? null;
      acceptFile(dropped);
    },
    [acceptFile],
  );

  const validationError = file ? describeFileProblem(file) : null;
  const blocked = Boolean(validationError);
  const canVerify = Boolean(file) && !blocked && !loading;

  return (
    <div>
      <div
        className={`upload-zone${dragOver ? " upload-zone--over" : ""}${
          file ? " upload-zone--filled" : ""
        }${loading ? " upload-zone--disabled" : ""}`}
        role="button"
        tabIndex={loading ? -1 : 0}
        aria-label={
          file
            ? `Selected file ${file.name}. Press Enter to choose a different file.`
            : "Upload a certificate file (PDF, JPG, JPEG, PNG)"
        }
        onClick={() => {
          if (!loading) inputRef.current?.click();
        }}
        onKeyDown={(e) => {
          if (!loading && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!loading) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          className="visually-hidden"
          onChange={(e) => acceptFile(e.target.files?.[0] ?? null)}
          aria-hidden="true"
          tabIndex={-1}
        />
        {file ? (
          <div className="file-chip">
            <span className="file-chip__filetype" aria-hidden="true">
              {formatFileType(file.name)}
            </span>
            <span style={{ minWidth: 0 }}>
              <span className="file-chip__name" title={file.name}>
                {file.name}
              </span>
              <span className="file-chip__meta">
                {formatBytes(file.size)}
              </span>
            </span>
            <button
              type="button"
              className="file-chip__remove"
              aria-label="Remove selected file"
              disabled={loading}
              onClick={(e) => {
                e.stopPropagation();
                acceptFile(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
            >
              ✕
            </button>
          </div>
        ) : (
          <>
            <span className="upload-zone__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <path d="M12 16v-5" />
                <path d="m9.5 13 2.5-2.5 2.5 2.5" />
              </svg>
            </span>
            <p className="upload-zone__title">Drag &amp; drop a certificate</p>
            <p className="upload-zone__subtitle">or click to browse your files</p>
            <p className="upload-zone__formats">PDF · JPG · JPEG · PNG (max 10 MB)</p>
          </>
        )}
      </div>

      {validationError ? (
        <p className="alert alert--error" role="alert" style={{ marginTop: 12 }}>
          {validationError}
        </p>
      ) : null}
      {error ? (
        <p className="alert alert--error" role="alert" style={{ marginTop: 12 }}>
          {error}
        </p>
      ) : null}

      <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn btn--primary btn--lg"
          onClick={onVerify}
          disabled={!canVerify}
        >
          {loading ? "Verifying…" : "Verify Certificate"}
        </button>
        {file && !blocked && !loading ? (
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => {
              acceptFile(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
          >
            Remove file
          </button>
        ) : null}
      </div>
    </div>
  );
}