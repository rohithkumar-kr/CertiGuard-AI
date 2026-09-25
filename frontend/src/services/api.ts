import type {
  AuditTrailResponse,
  FeedbackAnalytics,
  FeedbackRecord,
  FeedbackSummary,
  HealthResponse,
  MetricsResponse,
  ModelInfoResponse,
  ReviewerLabel,
  VerificationDetail,
  VerificationRecord,
  VerificationResponse,
  VerificationSummary,
} from "../types";
import {
  getAuthToken,
  refreshSessionToken,
  setAuthToken,
  triggerSessionExpired,
} from "./authToken";
import { classifyApiFailure, recoverFromAuthenticated401 } from "./authFlow";
import { bearerRequestInit } from "./httpHeaders";

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const RETRYABLE_DELAYS_MS = [400, 1200];

/**
 * Perform fetch with the standard transient-network-failure policy: idempotent
 * requests are retried with backoff; uploads are never retried (a verification
 * must not be submitted twice). Throws ApiError only on network failure --
 * HTTP error statuses are returned to the caller for classification.
 */
async function fetchWithRetry(path: string, init: RequestInit | undefined, authToken: string | null): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const idempotent = method === "GET" || method === "HEAD" || method === "OPTIONS";
  const attempts = idempotent ? 1 + RETRYABLE_DELAYS_MS.length : 1;

  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      return await fetch(`${API_BASE_URL}${path}`, bearerRequestInit(init, authToken));
    } catch (err) {
      // Transient network failure (backend worker restarting, connection
      // drop/reconnect). Retry idempotent requests; never retry uploads so a
      // verification is not submitted twice.
      if (attempt < attempts - 1) {
        await new Promise((r) => setTimeout(r, RETRYABLE_DELAYS_MS[attempt]));
        continue;
      }
      throw new ApiError(
        "Cannot reach the verification backend. Please make sure the backend server is running.",
      );
    }
  }
  throw new ApiError(
    "Cannot reach the verification backend. Please make sure the backend server is running.",
  );
}

async function responseDetail(response: Response): Promise<string> {
  if (response.headers.get("content-type")?.includes("application/json")) {
    try {
      const body = (await response.json()) as { detail?: string };
      return body?.detail ?? "";
    } catch {
      // ignore non-JSON error bodies
    }
  }
  return "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Read the token once per attempt. Requests fired before a session token
  // has been minted (e.g. right after sign-in, while Clerk token issuance is
  // still in flight) carry no Bearer header and must NOT be treated as
  // "session expired" -- otherwise the first protected call of a brand-new
  // session would sign the user out.
  const authToken = getAuthToken();
  let response = await fetchWithRetry(path, init, authToken);
  let attachedToken = authToken;

  // A 401 on a request that carried a Bearer token is the only response that
  // can indicate session expiration -- but only AFTER we rule out a stale-token
  // race. Ask the session provider for a genuinely fresh (uncached) token and
  // retry the request once with it. Only when no fresh token can be minted, or
  // the backend rejects the fresh token too, is the session treated as over.
  if (classifyApiFailure(response.status, attachedToken !== null) === "session-expired") {
    const { freshToken, recoverable } = await recoverFromAuthenticated401(refreshSessionToken);
    if (recoverable && freshToken) {
      setAuthToken(freshToken);
      attachedToken = freshToken;
      response = await fetchWithRetry(path, init, freshToken);
    }
  }

  if (classifyApiFailure(response.status, attachedToken !== null) === "session-expired") {
    triggerSessionExpired();
    throw new ApiError("Your session has expired. Please sign in again.", 401);
  }

  if (!response.ok) {
    const detail = await responseDetail(response);
    throw new ApiError(
      detail || `The backend returned an error (HTTP ${response.status}).`,
      response.status,
    );
  }

  return (await response.json()) as T;
}

export function verifyCertificate(file: File): Promise<VerificationResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<VerificationResponse>("/api/verify", {
    method: "POST",
    body: form,
  });
}

export function getVerifications(
  options: {
    limit?: number;
    search?: string;
    prediction?: string;
    certificateType?: string;
    sort?: "newest" | "oldest";
    reviewStatus?: string;
    issuer?: string;
    dateFrom?: string;
    dateTo?: string;
    riskMin?: number;
    riskMax?: number;
  } = {},
): Promise<VerificationRecord[]> {
  const params = new URLSearchParams();
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.search) params.set("search", options.search);
  if (options.prediction) params.set("prediction", options.prediction);
  if (options.certificateType) params.set("certificate_type", options.certificateType);
  if (options.sort) params.set("sort", options.sort);
  if (options.reviewStatus) params.set("review_status", options.reviewStatus);
  if (options.issuer) params.set("issuer", options.issuer);
  if (options.dateFrom) params.set("date_from", options.dateFrom);
  if (options.dateTo) params.set("date_to", options.dateTo);
  if (options.riskMin !== undefined) params.set("risk_min", String(options.riskMin));
  if (options.riskMax !== undefined) params.set("risk_max", String(options.riskMax));
  const qs = params.toString();
  return request<VerificationRecord[]>(`/api/verifications${qs ? `?${qs}` : ""}`);
}

export function getVerificationSummary(
  options: {
    search?: string;
    prediction?: string;
    certificateType?: string;
    reviewStatus?: string;
    issuer?: string;
  } = {},
): Promise<VerificationSummary> {
  const params = new URLSearchParams();
  if (options.search) params.set("search", options.search);
  if (options.prediction) params.set("prediction", options.prediction);
  if (options.certificateType) params.set("certificate_type", options.certificateType);
  if (options.reviewStatus) params.set("review_status", options.reviewStatus);
  if (options.issuer) params.set("issuer", options.issuer);
  const qs = params.toString();
  return request<VerificationSummary>(
    `/api/verifications/summary${qs ? `?${qs}` : ""}`,
  );
}

export function getMetrics(): Promise<MetricsResponse> {
  return request<MetricsResponse>("/api/metrics");
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

export function getModelInfo(): Promise<ModelInfoResponse> {
  return request<ModelInfoResponse>("/api/model/info");
}

export function getVerificationDetail(
  verificationId: string,
): Promise<VerificationDetail> {
  return request<VerificationDetail>(
    `/api/verifications/${encodeURIComponent(verificationId)}`,
  );
}

export function getVerificationAudit(
  verificationId: string,
): Promise<AuditTrailResponse> {
  return request<AuditTrailResponse>(
    `/api/verifications/${encodeURIComponent(verificationId)}/audit`,
  );
}

export function submitFeedback(
  verificationId: string,
  reviewerLabel: ReviewerLabel,
  reviewerNote?: string,
): Promise<FeedbackRecord> {
  return request<FeedbackRecord>(
    `/api/verifications/${encodeURIComponent(verificationId)}/feedback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewer_label: reviewerLabel,
        reviewer_note: reviewerNote ?? "",
      }),
    },
  );
}

export function getFeedbackSummary(): Promise<FeedbackSummary> {
  return request<FeedbackSummary>("/api/feedback/summary");
}

export function getFeedbackAnalytics(): Promise<FeedbackAnalytics> {
  return request<FeedbackAnalytics>("/api/feedback/analytics");
}
