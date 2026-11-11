import assert from "node:assert/strict";
import test from "node:test";
import { streamChat } from "../frontend/src/api.mjs";

test("streamChat handles split SSE frames and reports the conversation", async () => {
  const encoder = new TextEncoder();
  const frames = [
    "event: token\ndata: {\"delta\":\"Hello\"}\n\n",
    "event: token\ndata: {\"delta\":\" there\"}\n\n",
    "event: done\ndata: {\"conversation_id\":\"conv-1\",\"model\":\"test-model\"}\n\n",
  ].join("");
  const bytes = encoder.encode(frames);
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/v1/chat");
    assert.equal(JSON.parse(options.body).stream, true);
    let sent = false;
    return new Response(new ReadableStream({
      pull(controller) {
        if (sent) return controller.close();
        sent = true;
        controller.enqueue(bytes.slice(0, 19));
        controller.enqueue(bytes.slice(19));
        controller.close();
      },
    }), { status: 200 });
  };
  const tokens = [];
  const completion = await streamChat("Hi", null, (token) => tokens.push(token));
  assert.deepEqual(tokens, ["Hello", " there"]);
  assert.equal(completion.conversation_id, "conv-1");
});

test("streamChat surfaces server stream errors", async () => {
  globalThis.fetch = async () => new Response(
    "event: error\ndata: {\"message\":\"Model unavailable\"}\n\n",
    { status: 200 },
  );
  await assert.rejects(() => streamChat("Hi", null, () => {}), /Model unavailable/);
});
