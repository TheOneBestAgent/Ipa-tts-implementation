export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = process.env.TTS_BACKEND_URL || "http://127.0.0.1:8000";

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
]);

function stripHopByHop(headers: Headers): Headers {
  const out = new Headers();
  headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) out.set(key, value);
  });
  return out;
}

type Ctx = { params: Promise<{ path?: string[] }> };

async function handler(req: Request, ctx: Ctx) {
  const { path: parts = [] } = await ctx.params;
  const path = parts.join("/");
  const url = new URL(req.url);
  const upstreamUrl = `${BACKEND}/v1/dicts/${path}${url.search}`;

  const upstreamHeaders = stripHopByHop(req.headers);

  const method = req.method.toUpperCase();
  const body =
    method === "GET" || method === "HEAD" ? undefined : await req.arrayBuffer();

  const upstreamRes = await fetch(upstreamUrl, {
    method,
    headers: upstreamHeaders,
    body: body ? Buffer.from(body) : undefined,
    redirect: "manual",
  });

  const resHeaders = stripHopByHop(upstreamRes.headers);
  if (!resHeaders.has("cache-control")) resHeaders.set("cache-control", "no-store");

  return new Response(upstreamRes.body, {
    status: upstreamRes.status,
    headers: resHeaders,
  });
}

export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as PATCH,
  handler as DELETE,
  handler as HEAD,
};
