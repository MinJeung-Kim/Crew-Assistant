import { useState, useCallback } from "react";
import type { CrewGraph, Message } from "../types/chat";
import { generateId } from "../utils";
import { API_BASE, INITIAL_MESSAGE, SYSTEM_PROMPT } from "../constants";

function isCrewGraph(value: unknown): value is CrewGraph {
  if (!value || typeof value !== "object") return false;

  const graph = value as {
    topic?: unknown;
    target_year?: unknown;
    agents?: unknown;
    tasks?: unknown;
  };

  return (
    typeof graph.topic === "string" &&
    typeof graph.target_year === "number" &&
    Array.isArray(graph.agents) &&
    Array.isArray(graph.tasks)
  );
}

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
  const [crewGraph, setCrewGraph] = useState<CrewGraph | null>(null);

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
        {
          id: assistantId,
          role: "assistant",
          content: "",
          timestamp: new Date(),
          source: "llm",
        },
      ]);

      try {
        const res = await fetch(`${API_BASE}/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: historyPayload, session_id: sessionId }),
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        if (!res.body) {
          throw new Error("Empty response stream");
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let doneStreaming = false;

        while (!doneStreaming) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            const normalizedLine = line.trimEnd();
            if (!normalizedLine.startsWith("data: ")) continue;

            const payload = normalizedLine.slice(6).trim();
            if (payload === "[DONE]") {
              doneStreaming = true;
              break;
            }

            let token = payload;
            try {
              const parsed = JSON.parse(payload) as {
                token?: unknown;
                source?: unknown;
                crew_graph?: unknown;
              };
              if (typeof parsed.token === "string") {
                token = parsed.token;
              }

              if (isCrewGraph(parsed.crew_graph)) {
                setCrewGraph(parsed.crew_graph);
              }

              const parsedSource =
                typeof parsed.source === "string" ? parsed.source : undefined;
              if (parsedSource) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, source: parsedSource } : m
                  )
                );
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
    setCrewGraph(null);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return {
    messages,
    crewGraph,
    isLoading,
    error,
    sendMessage,
    resetSession,
    clearError,
  };
}