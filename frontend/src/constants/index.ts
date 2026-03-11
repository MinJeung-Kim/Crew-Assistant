export const API_BASE =
  (import.meta as unknown as { env: Record<string, string> }).env
    ?.VITE_API_BASE ?? "http://localhost:8000";

export const SYSTEM_PROMPT = "You are a helpful assistant.";

export const INITIAL_MESSAGE =
  "CrewAI 연동이 완료되었습니다. 예시: 2026년 IT 트랜드 조사해서 보고서 형식으로 요약해줘";