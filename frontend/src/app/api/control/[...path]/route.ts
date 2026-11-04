import { NextRequest, NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const resources =
  /^api\/(pools|boxes|deployments|workers)(?:\/[A-Za-z0-9_-]+){0,2}$/;
async function forward(
  request: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const path = params.path.join("/");
  const method = request.method;
  const allowed =
    (path === "health" && method === "GET") ||
    (resources.test(path) &&
      (method === "GET" ||
        (method === "POST" &&
          (/^api\/(pools|boxes|deployments)$/.test(path) ||
            /^api\/pools\/[^/]+\/rotate-code$/.test(path) ||
            /^api\/deployments\/[^/]+\/(stop|redeploy)$/.test(path) ||
            /^api\/workers\/[^/]+\/disconnect$/.test(path))) ||
        (method === "DELETE" &&
          /^api\/(boxes|workers|pools)\/[^/]+$/.test(path))));
  if (!allowed || params.path.some((p) => !/^[A-Za-z0-9_-]+$/.test(p)))
    return NextResponse.json(
      { detail: "Unsupported management operation." },
      { status: 404 },
    );
  const authorization = request.headers.get("authorization");
  if (path !== "health" && !authorization?.startsWith("Bearer "))
    return NextResponse.json(
      { detail: "Operator authorization required." },
      { status: 401 },
    );
  try {
    const origin = new URL(
      process.env.CONTROL_PLANE_URL || "http://127.0.0.1:8000",
    );
    if (
      origin.username ||
      origin.password ||
      origin.search ||
      origin.hash ||
      origin.pathname !== "/" ||
      !(
        origin.protocol === "https:" ||
        (origin.protocol === "http:" &&
          ["localhost", "127.0.0.1", "[::1]"].includes(origin.hostname))
      )
    )
      throw new Error("Invalid configured controller origin");
    const target = new URL("/" + path, origin);
    target.search = request.nextUrl.search;
    const headers = new Headers({ Accept: "application/json" });
    if (authorization) headers.set("Authorization", authorization);
    let body: string | undefined;
    if (method === "POST") {
      const reader = request.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader) {
        while (true) {
          const next = await reader.read();
          if (next.done) break;
          size += next.value.byteLength;
          if (size > 65536) {
            await reader.cancel();
            return NextResponse.json(
              { detail: "Request is too large." },
              { status: 413 },
            );
          }
          chunks.push(next.value);
        }
      }
      body = Buffer.concat(chunks).toString("utf8");
      headers.set("Content-Type", "application/json");
    }
    const upstream = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(25000),
    });
    if (upstream.status === 204)
      return new Response(null, {
        status: 204,
        headers: { "Cache-Control": "no-store" },
      });
    if (!upstream.headers.get("content-type")?.includes("application/json"))
      return NextResponse.json(
        {
          detail:
            "Controller returned a non-JSON response. Check the tunnel/origin.",
        },
        { status: 502 },
      );
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        detail:
          "Controller unavailable. Check CONTROL_PLANE_URL, the server and tunnel.",
      },
      { status: 502 },
    );
  }
}
export { forward as GET, forward as POST, forward as DELETE };
