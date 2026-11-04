import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET as forward } from "../src/app/api/control/[...path]/route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const request = (
  path: string,
  method = "GET",
  token = "fixture-token",
  body?: string,
) =>
  new NextRequest("http://localhost:3000/api/control/" + path, {
    method,
    headers: token ? { Authorization: "Bearer " + token } : {},
    body,
  });
it("requires credentials for protected routes before contacting the controller", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  expect(
    (
      await forward(request("api/pools", "GET", ""), {
        params: { path: ["api", "pools"] },
      })
    ).status,
  ).toBe(401);
  expect(fetch).not.toHaveBeenCalled();
});
it("blocks arbitrary URLs and unsupported credential operations", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  expect(
    (
      await forward(request("api/workers/a/rotate-token", "POST"), {
        params: { path: ["api", "workers", "a", "rotate-token"] },
      })
    ).status,
  ).toBe(404);
  expect(fetch).not.toHaveBeenCalled();
});
it("forwards only to the configured controller without caching or following redirects", async () => {
  vi.stubEnv("CONTROL_PLANE_URL", "https://api.example.com");
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response("[]", { headers: { "Content-Type": "application/json" } }),
    );
  vi.stubGlobal("fetch", fetch);
  const response = await forward(request("api/pools"), {
    params: { path: ["api", "pools"] },
  });
  expect(response.status).toBe(200);
  expect(String(fetch.mock.calls[0][0])).toBe(
    "https://api.example.com/api/pools",
  );
  expect(fetch.mock.calls[0][1]).toMatchObject({
    cache: "no-store",
    redirect: "error",
  });
  expect(response.headers.get("cache-control")).toBe("no-store");
});
it("preserves backend conflict status and details", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response('{"detail":"Pool exists"}', {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  const res = await forward(
    request("api/pools", "POST", undefined, '{"name":"development"}'),
    { params: { path: ["api", "pools"] } },
  );
  expect(res.status).toBe(409);
  expect(await res.json()).toEqual({ detail: "Pool exists" });
});
it("bounds the incoming JSON body before sending it upstream", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const res = await forward(
    request("api/pools", "POST", undefined, "x".repeat(65537)),
    { params: { path: ["api", "pools"] } },
  );
  expect(res.status).toBe(413);
  expect(fetch).not.toHaveBeenCalled();
});
it("does not return upstream HTML as an apparent successful API response", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response("<html>tunnel unavailable</html>", {
        headers: { "Content-Type": "text/html" },
      }),
    ),
  );
  expect(
    (await forward(request("health"), { params: { path: ["health"] } })).status,
  ).toBe(502);
});
it("does not leak a misconfigured upstream URL's credentials", async () => {
  vi.stubEnv("CONTROL_PLANE_URL", "https://user:private-pass@api.example");
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const res = await forward(request("health"), {
    params: { path: ["health"] },
  });
  expect(res.status).toBe(502);
  expect(await res.text()).not.toContain("private-pass");
  expect(fetch).not.toHaveBeenCalled();
});

it.each(["workers", "pools"])(
  "forwards authenticated %s deletion and accepts no-content success",
  async (resource) => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);
    const response = await forward(
      request(`api/${resource}/fixture-id`, "DELETE"),
      { params: { path: ["api", resource, "fixture-id"] } },
    );
    expect(response.status).toBe(204);
    expect(fetch.mock.calls[0][1].method).toBe("DELETE");
  },
);
it("does not allow deletion to nested worker operations", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const response = await forward(request("api/workers/a/snapshot", "DELETE"), {
    params: { path: ["api", "workers", "a", "snapshot"] },
  });
  expect(response.status).toBe(404);
  expect(fetch).not.toHaveBeenCalled();
});
