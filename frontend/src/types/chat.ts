// src/types/chat.ts

export interface Message {
  id: string;
  role: "assistant" | "user";
  content: string;
  timestamp: Date;
  source?: string;
}

export interface ChatPayloadMessage {
  role: string;
  content: string;
}

export interface CrewGraphAgent {
  id: string;
  role: string;
  goal: string;
}

export interface CrewGraphTask {
  id: string;
  title: string;
  agent_id: string;
  depends_on: string[];
  description?: string;
  expected_output?: string;
}

export interface CrewGraph {
  topic: string;
  target_year: number;
  agents: CrewGraphAgent[];
  tasks: CrewGraphTask[];
}

export type CrewTaskStatus = "pending" | "running" | "completed" | "failed";

export interface CrewProgressTask {
  task_id: string;
  title: string;
  agent_id: string;
  status: CrewTaskStatus;
}

export interface CrewProgress {
  phase: string;
  active_task_id: string | null;
  active_agent_id: string | null;
  detail?: string | null;
  updated_at: string;
  tasks: CrewProgressTask[];
}