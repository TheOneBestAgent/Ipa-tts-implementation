import assert from "node:assert/strict";
import { test } from "node:test";

import { GET } from "../app/api/dicts/[...path]/route";

test("api dicts proxy returns JSON", async () => {
  let seenUrl = "";
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    seenUrl = typeof input === "string" ? input : input.url;
    return new Response(JSON.stringify({ key: "gojo" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  try {
    const req = new Request("http://localhost:3000/api/dicts/lookup?key=gojo");
    const res = await GET(req, { params: Promise.resolve({ path: ["lookup"] }) });
    const data = await res.json();
    assert.equal(data.key, "gojo");
    assert.ok(seenUrl.includes("/v1/dicts/lookup?key=gojo"));
  } finally {
    globalThis.fetch = originalFetch;
  }
});
