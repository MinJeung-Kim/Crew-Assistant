import type { CrewGraph, CrewProgress, Message } from "../types/chat";

function sanitizeSessionName(sessionName: string): string {
  const normalized = sessionName
    .replace(/[^a-zA-Z0-9-_]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return normalized || "session";
}

function timestampForFilename(date: Date): string {
  return date.toISOString().replace(/:/g, "-");
}

export function buildDownloadFileName(prefix: string, sessionName: string, exportedAt: Date, ext: string): string {
  const safeSession = sanitizeSessionName(sessionName);
  return `${prefix}-${safeSession}-${timestampForFilename(exportedAt)}.${ext}`;
}

export function buildMarkdownExport(sessionName: string, exportedAt: Date, messages: Message[]): string {
  return [
    "# Chat Export",
    "",
    `- Session: ${sessionName}`,
    `- Exported At: ${exportedAt.toISOString()}`,
    "",
    ...messages.map((msg) => {
      const roleLabel = msg.role === "user" ? "User" : "Assistant";
      const sourceLine = msg.source ? `- Source: ${msg.source}\n` : "";
      return `## ${roleLabel}\n- Time: ${msg.timestamp.toISOString()}\n${sourceLine}\n${msg.content}\n`;
    }),
  ].join("\n");
}

export function buildHistoryExportPayload(
  sessionName: string,
  exportedAt: Date,
  messages: Message[],
  crewGraph: CrewGraph | null,
  crewProgress: CrewProgress | null,
): Record<string, unknown> {
  return {
    session: sessionName,
    exported_at: exportedAt.toISOString(),
    entries: messages.map((msg) => ({
      role: msg.role,
      source: msg.source ?? null,
      timestamp: msg.timestamp.toISOString(),
      content: msg.content,
    })),
    crew_graph: crewGraph,
    crew_progress: crewProgress,
  };
}

export function buildCrewReportExport(sessionName: string, exportedAt: Date, messages: Message[]): string {
  const reportMessages = messages.filter((m) => m.source === "crewai");
  return [
    `- Session: ${sessionName}`,
    `- Exported At: ${exportedAt.toISOString()}`,
    "",
    ...reportMessages.map((msg) =>
      msg.showTranslated && msg.translatedContent ? msg.translatedContent : msg.content
    ),
  ].join("\n");
}

export type DownloadFormat = "md" | "pdf" | "doc";

function escapeHtmlPreservingBr(md: string): string {
  // Temporarily replace <br> before escaping, then restore
  const BR = "\x00BR\x00";
  return md
    .replace(/<br\s*\/?>/gi, BR)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(new RegExp(BR, "g"), "<br>");
}

function isTableRow(line: string): boolean {
  return /^\s*\|.+\|\s*$/.test(line);
}

function isSeparatorRow(line: string): boolean {
  return /^\s*\|[\s|:\-]+\|\s*$/.test(line) && /--/.test(line);
}

function renderTable(rows: string[]): string {
  const out: string[] = ["<table>"];
  let isHeader = true;
  for (const row of rows) {
    if (isSeparatorRow(row)) {
      isHeader = false;
      continue;
    }
    const cells = row.split("|").slice(1, -1);
    const tag = isHeader ? "th" : "td";
    out.push(`<tr>${cells.map((c) => `<${tag}>${c.trim()}</${tag}>`).join("")}</tr>`);
    if (isHeader) isHeader = false;
  }
  out.push("</table>");
  return out.join("\n");
}

function markdownToHtml(md: string): string {
  const safe = escapeHtmlPreservingBr(md);
  const lines = safe.split("\n");
  const out: string[] = [];
  let inList = false;
  let tableBuffer: string[] = [];

  const closeList = () => { if (inList) { out.push("</ul>"); inList = false; } };
  const flushTable = () => {
    if (tableBuffer.length === 0) return;
    closeList();
    out.push(renderTable(tableBuffer));
    tableBuffer = [];
  };

  for (const raw of lines) {
    if (isTableRow(raw)) {
      closeList();
      tableBuffer.push(raw);
      continue;
    }
    flushTable();

    const h4 = /^#### (.+)/.exec(raw);
    const h3 = /^### (.+)/.exec(raw);
    const h2 = /^## (.+)/.exec(raw);
    const h1 = /^# (.+)/.exec(raw);
    const li = /^[-*] (.+)/.exec(raw);
    const isHr = /^---+$/.test(raw.trim());

    if (h4) { closeList(); out.push(`<h4>${h4[1]}</h4>`); }
    else if (h3) { closeList(); out.push(`<h3>${h3[1]}</h3>`); }
    else if (h2) { closeList(); out.push(`<h2>${h2[1]}</h2>`); }
    else if (h1) { closeList(); out.push(`<h1>${h1[1]}</h1>`); }
    else if (isHr) { closeList(); out.push("<hr>"); }
    else if (li) { if (!inList) { out.push("<ul>"); inList = true; } out.push(`<li>${li[1]}</li>`); }
    else if (raw.trim() === "") { closeList(); }
    else { closeList(); out.push(`<p>${raw}</p>`); }
  }
  flushTable();
  if (inList) out.push("</ul>");

  return out
    .join("\n")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
}

export function downloadReportAsPdf(title: string, body: string): void {
  const htmlBody = markdownToHtml(body);
  const html = `<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>${title}</title>
  <style>
    body { font-family: Georgia, "Times New Roman", serif; max-width: 820px; margin: 40px auto; padding: 0 20px; line-height: 1.8; color: #1a1a1a; font-size: 14px; }
    h1 { font-size: 1.8em; border-bottom: 2px solid #333; padding-bottom: 8px; }
    h2 { font-size: 1.4em; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 2em; }
    h3 { font-size: 1.2em; color: #333; }
    h4 { font-size: 1em; color: #555; }
    ul { padding-left: 1.5em; } li { margin: 4px 0; }
    hr { border: none; border-top: 1px solid #ddd; margin: 2em 0; }
    p { margin: 0.8em 0; }
    table { border-collapse: collapse; width: 100%; margin: 1.2em 0; font-size: 12px; }
    th, td { border: 1px solid #bbb; padding: 6px 10px; text-align: left; vertical-align: top; }
    th { background: #f0f0f0; font-weight: bold; white-space: nowrap; }
    tr:nth-child(even) td { background: #f9f9f9; }
    @media print { body { margin: 10mm; max-width: 100%; } table { font-size: 10px; } }
  </style>
</head>
<body>
${htmlBody}
</body>
</html>`;

  const win = window.open("", "_blank", "width=900,height=700");
  if (!win) return;
  win.document.open();
  win.document.write(html);
  win.document.close();
  setTimeout(() => win.print(), 300);
}

export function downloadReportAsDoc(title: string, body: string, fileName: string): void {
  const htmlBody = markdownToHtml(body);
  const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:w="urn:schemas-microsoft-com:office:word"
  xmlns="http://www.w3.org/TR/REC-html40">
<head>
  <meta charset="utf-8">
  <title>${title}</title>
  <style>
    body { font-family: "Malgun Gothic", Arial, sans-serif; font-size: 11pt; line-height: 1.6; }
    h1 { font-size: 18pt; } h2 { font-size: 14pt; } h3 { font-size: 12pt; }
    ul { margin-left: 1.5em; } li { margin: 2pt 0; }
    table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 10pt; }
    th, td { border: 1px solid #999; padding: 4px 8px; text-align: left; vertical-align: top; }
    th { background: #e8e8e8; font-weight: bold; }
  </style>
</head>
<body>
${htmlBody}
</body>
</html>`;
  triggerBlobDownload(html, "application/msword", fileName);
}

export function triggerBlobDownload(content: string, contentType: string, fileName: string): void {
  const blob = new Blob([content], {
    type: contentType,
  });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  URL.revokeObjectURL(url);
}
