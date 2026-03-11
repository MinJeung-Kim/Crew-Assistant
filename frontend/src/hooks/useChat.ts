import { useState, useCallback } from "react";
import type { Message } from "../types/chat";
import { generateId } from "../utils";
import { API_BASE, INITIAL_MESSAGE, SYSTEM_PROMPT } from "../constants";

function makeInitialMessage(): Message {
  return {
    id: generateId(),
    role: "assistant",
    content: INITIAL_MESSAGE,
    timestamp: new Date(Date.now() - 3 * 60_000),
  };
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([makeInitialMessage()]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (input: string, sessionId: string) => {
      if (!input.trim() || isLoading) return;
      setError(null);

      const userMsg: Message = {
        id: generateId(),
        role: "user",
        content: input.trim(),
        timestamp: new Date(),
        source: "openclaw-control-ui",
      };

      const historyPayload = [
        { role: "system", content: SYSTEM_PROMPT },
        ...messages.map((m) => ({ role: m.role, content: m.content })),
        { role: "user", content: userMsg.content },
      ];

      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      const assistantId = generateId();
      setMessages((prev) => [
        ...prev,
        { id: assistantId, role: "assistant", content: "", timestamp: new Date() },
      ]);

      try {
        const res = await fetch(`${API_BASE}/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: historyPayload, session_id: sessionId }),
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.slice(6);
            if (payload === "[DONE]") break;

            let token = payload;
            try {
              const parsed = JSON.parse(payload) as { token?: unknown };
              if (typeof parsed.token === "string") {
                token = parsed.token;
              }
            } catch {
              // Fallback for legacy non-JSON streaming payloads.
            }

            if (!token) continue;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + token } : m
              )
            );
          }
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setError(`LLM request failed: ${msg}`);
        setMessages((prev) => prev.filter((m) => m.id !== assistantId));
      } finally {
        setIsLoading(false);
      }
    },
    [messages, isLoading]
  );

  const resetSession = useCallback(() => {
    setMessages([makeInitialMessage()]);
    setError(null);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { messages, isLoading, error, sendMessage, resetSession, clearError };
}