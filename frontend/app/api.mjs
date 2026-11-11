const API = "/api/v1";

export const json = (data) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await response.json() : await response.blob();
  if (!response.ok) throw new Error(data?.error?.message || data?.detail || `Request failed (${response.status})`);
  return data;
}

export async function streamChat(message, conversationId, onToken) {
  const response = await fetch(`${API}/chat`, {
    ...json({ message, ...(conversationId ? { conversation_id: conversationId } : {}), stream: true }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data?.error?.message || `Chat request failed (${response.status})`);
  }
  if (!response.body) throw new Error("The response stream is unavailable.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completion = null;
  let received = false;

  const consume = (block) => {
    const kind = block.match(/^event:\s*(.+)$/m)?.[1]?.trim();
    const payload = block.match(/^data:\s*(.+)$/m)?.[1];
    if (!payload) return;
    const data = JSON.parse(payload);
    if (kind === "token") {
      received = true;
      onToken(data.delta || "");
    } else if (kind === "done") {
      completion = data;
    } else if (kind === "error") {
      throw new Error(data.message || "The response stream failed.");
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.replaceAll("\r\n", "\n").split("\n\n");
    buffer = blocks.pop() || "";
    blocks.forEach(consume);
    if (done) break;
  }
  if (buffer.trim()) consume(buffer);
  if (!completion) throw new Error(received ? "The response stream ended before EIVA finished." : "EIVA returned an empty response.");
  return completion;
}
