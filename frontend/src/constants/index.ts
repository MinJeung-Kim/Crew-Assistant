export const API_BASE =
  (import.meta as unknown as { env: Record<string, string> }).env
    ?.VITE_API_BASE ?? "http://localhost:8000";

export const SYSTEM_PROMPT = "You are a helpful assistant.";

export const INITIAL_MESSAGE =
  "안녕하세요 😊 무엇을 도와드릴까요?";