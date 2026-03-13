import { useState, useCallback, useRef } from "react";
import type { CrewGraph, CrewProgress, Message } from "../types/chat";
import { generateId } from "../utils";
import { API_BASE, INITIAL_MESSAGE, SYSTEM_PROMPT } from "../constants";
import { parseSseChunk } from "../services/chatStream";

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

          const chunkText = decoder.decode(value, { stream: true });
          const parsedChunk = parseSseChunk(chunkText, buffer);
          buffer = parsedChunk.pendingBuffer;

          for (const event of parsedChunk.events) {
            if (event.done) {
              doneStreaming = true;
              break;
            }

            if (event.crewGraph) {
              setCrewGraph(event.crewGraph);
            }

            if (event.crewProgress) {
              setCrewProgress(event.crewProgress);
            }

            if (event.source) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, source: event.source } : m
                )
              );
              if (event.source === "llm") {
                setCrewProgress(null);
              }
            }

            if (!event.token) {
              continue;
            }

            receivedToken = true;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + event.token } : m
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

  const updateMessageTranslation = useCallback(
    (id: string, translatedContent: string, showTranslated: boolean) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id ? { ...m, translatedContent, showTranslated } : m
        )
      );
    },
    []
  );

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
    updateMessageTranslation,
  };
}