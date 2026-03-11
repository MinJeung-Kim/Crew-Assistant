import { useState, useCallback, useRef } from "react";
import type { CrewGraph, CrewProgress, CrewTaskStatus, Message } from "../types/chat";
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

function isCrewTaskStatus(value: unknown): value is CrewTaskStatus {
  return value === "pending" || value === "running" || value === "completed" || value === "failed";
}

function isCrewProgress(value: unknown): value is CrewProgress {
  if (!value || typeof value !== "object") return false;

  const progress = value as {
    phase?: unknown;
    active_task_id?: unknown;
    active_agent_id?: unknown;
    updated_at?: unknown;
    tasks?: unknown;
  };

  if (typeof progress.phase !== "string") return false;
  if (!(typeof progress.active_task_id === "string" || progress.active_task_id === null)) {
    return false;
  }
  if (!(typeof progress.active_agent_id === "string" || progress.active_agent_id === null)) {
    return false;
  }
  if (typeof progress.updated_at !== "string") return false;
  if (!Array.isArray(progress.tasks)) return false;

  return progress.tasks.every((task) => {
    if (!task || typeof task !== "object") return false;
    const taskItem = task as {
      task_id?: unknown;
      title?: unknown;
      agent_id?: unknown;
      status?: unknown;
    };
    return (
      typeof taskItem.task_id === "string" &&
      typeof taskItem.title === "string" &&
      typeof taskItem.agent_id === "string" &&
      isCrewTaskStatus(taskItem.status)
    );
  });
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
  const abortControllerRef = useRef<AbortController | null>(null);
  const [crewProgress, setCrewProgress] = useState<CrewProgress | null>(null);

  const sendMessage = useCallback(
    async (input: string, sessionId: string) => {
      if (!input.trim() || isLoading) return;
      setError(null);
      setCrewProgress(null);

      const userMsg: Message = {
        id: generateId(),
        role: "user",
        content: input.trim(),
        timestamp: new Date(),
        source: "Orchestration-control-ui",
      };

      const historyPayload = [
        { role: "system", content: SYSTEM_PROMPT },
        ...messages.map((m) => ({ role: m.role, content: m.content })),
        { role: "user", content: userMsg.content },
      ];

      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      const assistantId = generateId();
      const streamController = new AbortController();
      abortControllerRef.current = streamController;
      let receivedToken = false;

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
          signal: streamController.signal,
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
                crew_progress?: unknown;
              };
              if (typeof parsed.token === "string") {
                token = parsed.token;
              }

              if (isCrewGraph(parsed.crew_graph)) {
                setCrewGraph(parsed.crew_graph);
              }

              if (isCrewProgress(parsed.crew_progress)) {
                setCrewProgress(parsed.crew_progress);
              }

              const parsedSource =
                typeof parsed.source === "string" ? parsed.source : undefined;
              if (parsedSource) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, source: parsedSource } : m
                  )
                );
                if (parsedSource === "llm") {
                  setCrewProgress(null);
                }
              }
            } catch {
              // Fallback for legacy non-JSON streaming payloads.
            }

            if (!token) continue;
            receivedToken = true;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + token } : m
              )
            );
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          if (!receivedToken) {
            setMessages((prev) => prev.filter((m) => m.id !== assistantId));
          }
          return;
        }

        const msg = err instanceof Error ? err.message : "Unknown error";
        setError(`LLM request failed: ${msg}`);
        setMessages((prev) => prev.filter((m) => m.id !== assistantId));
      } finally {
        if (abortControllerRef.current === streamController) {
          abortControllerRef.current = null;
        }
        setIsLoading(false);
      }
    },
    [messages, isLoading]
  );

  const stopStreaming = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  const appendAssistantMessage = useCallback(
    (content: string, source = "system") => {
      const normalized = content.trim();
      if (!normalized) return;

      setMessages((prev) => [
        ...prev,
        {
          id: generateId(),
          role: "assistant",
          content: normalized,
          timestamp: new Date(),
          source,
        },
      ]);
    },
    []
  );

  const resetSession = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setIsLoading(false);
    setMessages([makeInitialMessage()]);
    setError(null);
    setCrewGraph(null);
    setCrewProgress(null);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return {
    messages,
    crewGraph,
    crewProgress,
    isLoading,
    error,
    sendMessage,
    stopStreaming,
    appendAssistantMessage,
    resetSession,
    clearError,
  };
}