import { API_BASE } from "../constants";

interface UploadKnowledgeApiPayload {
  detail?: unknown;
  chunk_count?: unknown;
  total_chunks?: unknown;
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

  const payload = (await response.json().catch(() => ({}))) as UploadKnowledgeApiPayload;

  if (!response.ok) {
    const detail =
      typeof payload.detail === "string"
        ? payload.detail
        : `HTTP ${response.status}`;
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
