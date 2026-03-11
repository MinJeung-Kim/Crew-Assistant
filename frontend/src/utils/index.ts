export function formatTime(date: Date): string {
  return date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

export function generateId(): string {
  return Math.random().toString(36).slice(2, 9);
}