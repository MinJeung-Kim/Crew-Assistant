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