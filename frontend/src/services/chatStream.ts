import type { CrewGraph, CrewProgress, CrewTaskStatus } from "../types/chat";

export interface ParsedChatStreamEvent {
  token: string;
  source?: string;
  crewGraph?: CrewGraph;
  crewProgress?: CrewProgress;
  done: boolean;
}

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

function parseSsePayload(payload: string): ParsedChatStreamEvent | null {
  if (payload === "[DONE]") {
    return { token: "", done: true };
  }

  if (!payload) {
    return null;
  }

  try {
    const parsed = JSON.parse(payload) as {
      token?: unknown;
      source?: unknown;
      crew_graph?: unknown;
      crew_progress?: unknown;
    };

    const event: ParsedChatStreamEvent = {
      token: typeof parsed.token === "string" ? parsed.token : "",
      done: false,
    };

    if (typeof parsed.source === "string") {
      event.source = parsed.source;
    }
    if (isCrewGraph(parsed.crew_graph)) {
      event.crewGraph = parsed.crew_graph;
    }
    if (isCrewProgress(parsed.crew_progress)) {
      event.crewProgress = parsed.crew_progress;
    }

    if (!event.token && !event.source && !event.crewGraph && !event.crewProgress) {
      return null;
    }

    return event;
  } catch {
    return { token: payload, done: false };
  }
}

export function parseSseChunk(
  rawChunk: string,
  pendingBuffer: string,
): { events: ParsedChatStreamEvent[]; pendingBuffer: string } {
  const lines = `${pendingBuffer}${rawChunk}`.split("\n");
  const nextBuffer = lines.pop() ?? "";
  const events: ParsedChatStreamEvent[] = [];

  for (const line of lines) {
    const normalizedLine = line.trimEnd();
    if (!normalizedLine.startsWith("data: ")) {
      continue;
    }

    const payload = normalizedLine.slice(6).trim();
    const event = parseSsePayload(payload);
    if (event) {
      events.push(event);
    }
  }

  return { events, pendingBuffer: nextBuffer };
}
