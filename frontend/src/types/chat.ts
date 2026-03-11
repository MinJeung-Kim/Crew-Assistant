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
}

export interface CrewGraph {
  topic: string;
  target_year: number;
  agents: CrewGraphAgent[];
  tasks: CrewGraphTask[];
}