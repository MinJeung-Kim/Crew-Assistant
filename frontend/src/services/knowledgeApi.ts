import { API_BASE } from "../constants";

interface UploadKnowledgeApiPayload {
  detail?: unknown;
  chunk_count?: unknown;
  total_chunks?: unknown;
}

function extractApiErrorMessage(detail: unknown): string | null {
  if (typeof detail === "string") {
    const normalized = detail.trim();
    return normalized || null;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") {
          return item.trim();
        }

        if (!item || typeof item !== "object") {
          return "";
        }

        const record = item as {
          msg?: unknown;
          loc?: unknown;
        };

        const msg = typeof record.msg === "string" ? record.msg.trim() : "";
        const loc = Array.isArray(record.loc)
          ? record.loc.map((token) => String(token)).join(".")
          : "";

        if (msg && loc) {
          return `${loc}: ${msg}`;
        }

        return msg;
      })
      .filter((msg) => msg.length > 0);

    return messages.length > 0 ? messages.join("; ") : null;
  }

  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    for (const key of ["message", "error", "detail"]) {
      if (typeof record[key] === "string") {
        const value = record[key].trim();
        if (value) {
          return value;
        }
      }
    }
  }

  return null;
}

export interface KnowledgeUploadResult {
  chunkCount: number;
  totalChunks: number;
}

export async function uploadKnowledgeFile(file: File): Promise<KnowledgeUploadResult> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/knowledge/upload`, {
    method: "POST",
    body: formData,
  });

  const rawBody = await response.text();
  let payload: UploadKnowledgeApiPayload = {};
  if (rawBody.trim()) {
    try {
      payload = JSON.parse(rawBody) as UploadKnowledgeApiPayload;
    } catch {
      payload = {};
    }
  }

  if (!response.ok) {
    const detail =
      extractApiErrorMessage(payload.detail) ||
      (rawBody.trim() ? rawBody.trim() : `HTTP ${response.status}`);
    throw new Error(detail);
  }

  const chunkCount =
    typeof payload.chunk_count === "number" ? payload.chunk_count : 0;
  const totalChunks =
    typeof payload.total_chunks === "number"
      ? payload.total_chunks
      : chunkCount;

  return {
    chunkCount,
    totalChunks,
  };
}
