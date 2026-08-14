import assert from "node:assert/strict";
import test from "node:test";

import worker, { __test } from "./index.js";

const ORIGIN = "https://ko-72.com";
const SECRET = "test-only-unsubscribe-secret-32-chars-minimum";

function makeRequest(path, body, headers = {}) {
  return new Request(`https://subscribe.ko-72.com${path}`, {
    method: "POST",
    headers: {
      Origin: ORIGIN,
      "Content-Type": "application/json",
      "CF-Connecting-IP": "203.0.113.10",
      ...headers,
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

function makeLimiter(outcomes = []) {
  const calls = [];
  return {
    calls,
    async limit(options) {
      calls.push(options);
      return { success: outcomes.length ? outcomes.shift() : true };
    },
  };
}

function makeEnv(overrides = {}) {
  return {
    BUTTONDOWN_API_KEY: "buttondown-test-key",
    RESEND_API_KEY: "resend-test-key",
    UNSUBSCRIBE_TOKEN_SECRET: SECRET,
    SUBSCRIBE_RATE_LIMITER: makeLimiter(),
    UNSUBSCRIBE_RATE_LIMITER: makeLimiter(),
    ...overrides,
  };
}

async function withMockFetch(mock, operation) {
  const original = globalThis.fetch;
  globalThis.fetch = mock;
  try {
    return await operation();
  } finally {
    globalThis.fetch = original;
  }
}

async function responseJson(response) {
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), ORIGIN);
  assert.match(response.headers.get("Content-Type"), /^application\/json/);
  return response.json();
}

test("season 71 date range crosses into January without a negative duration", () => {
  const season71 = {
    id: 71,
    start_month: 12,
    start_day: 27,
  };

  assert.deepEqual(__test.getSeasonDateRange(season71), {
    dateRange: "Dec 27 – Dec 31",
    duration: 5,
  });
  assert.deepEqual(__test.getSeasonDateRangeForLang(season71, "ja"), {
    dateRange: "12月27日 – 12月31日",
    duration: 5,
  });
});

test("invalid JSON and invalid email fail before any upstream mutation", async () => {
  let upstreamCalls = 0;
  await withMockFetch(async () => {
    upstreamCalls += 1;
    throw new Error("unexpected upstream request");
  }, async () => {
    const malformed = await worker.fetch(makeRequest("/unsubscribe", "{"), makeEnv());
    assert.equal(malformed.status, 400);
    assert.equal((await responseJson(malformed)).code, "invalid_json");

    const invalidEmail = await worker.fetch(makeRequest("/subscribe", { email: "not-an-email" }), makeEnv());
    assert.equal(invalidEmail.status, 400);
    assert.equal((await responseJson(invalidEmail)).code, "invalid_email");
  });
  assert.equal(upstreamCalls, 0);
});

test("disallowed Origin is rejected before rate limiting or upstream calls", async () => {
  const subscribeLimiter = makeLimiter();
  const unsubscribeLimiter = makeLimiter();
  let upstreamCalls = 0;
  const response = await withMockFetch(async () => {
    upstreamCalls += 1;
    throw new Error("unexpected upstream request");
  }, () => worker.fetch(
    makeRequest("/unsubscribe", { email: "reader@example.com" }, { Origin: "https://attacker.example" }),
    makeEnv({
      SUBSCRIBE_RATE_LIMITER: subscribeLimiter,
      UNSUBSCRIBE_RATE_LIMITER: unsubscribeLimiter,
    }),
  ));

  assert.equal(response.status, 403);
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), null);
  assert.equal((await response.json()).code, "cors_forbidden");
  assert.equal(subscribeLimiter.calls.length, 0);
  assert.equal(unsubscribeLimiter.calls.length, 0);
  assert.equal(upstreamCalls, 0);
});

test("oversized JSON is rejected before rate limiting or upstream calls", async () => {
  const limiter = makeLimiter();
  let upstreamCalls = 0;
  const oversizedBody = JSON.stringify({ email: `${"a".repeat(5000)}@example.com` });
  const response = await withMockFetch(async () => {
    upstreamCalls += 1;
    throw new Error("unexpected upstream request");
  }, () => worker.fetch(
    makeRequest("/unsubscribe", oversizedBody),
    makeEnv({ UNSUBSCRIBE_RATE_LIMITER: limiter }),
  ));

  assert.equal(response.status, 413);
  assert.equal((await responseJson(response)).code, "payload_too_large");
  assert.equal(limiter.calls.length, 0);
  assert.equal(upstreamCalls, 0);
});

test("known route with the wrong method returns 405 and Allow without side effects", async () => {
  const subscribeLimiter = makeLimiter();
  let upstreamCalls = 0;
  const request = new Request("https://subscribe.ko-72.com/subscribe", {
    method: "GET",
    headers: { Origin: ORIGIN },
  });
  const response = await withMockFetch(async () => {
    upstreamCalls += 1;
    throw new Error("unexpected upstream request");
  }, () => worker.fetch(
    request,
    makeEnv({ SUBSCRIBE_RATE_LIMITER: subscribeLimiter }),
  ));

  assert.equal(response.status, 405);
  assert.equal(response.headers.get("Allow"), "POST, OPTIONS");
  assert.equal((await responseJson(response)).code, "method_not_allowed");
  assert.equal(subscribeLimiter.calls.length, 0);
  assert.equal(upstreamCalls, 0);
});

test("tampered and missing unsubscribe tokens never call Buttondown", async () => {
  const valid = await __test.createUnsubscribeToken(SECRET, "reader@example.com");
  const [payload, signature] = valid.split(".");
  const tampered = `${payload}.${signature[0] === "A" ? "B" : "A"}${signature.slice(1)}`;
  const expired = await __test.createUnsubscribeToken(SECRET, "reader@example.com", 1_000);
  let upstreamCalls = 0;

  await withMockFetch(async () => {
    upstreamCalls += 1;
    throw new Error("unexpected Buttondown mutation");
  }, async () => {
    const noToken = await worker.fetch(makeRequest("/unsubscribe/confirm", {}), makeEnv());
    assert.equal(noToken.status, 401);
    assert.equal((await responseJson(noToken)).code, "invalid_token");

    const badToken = await worker.fetch(makeRequest("/unsubscribe/confirm", { token: tampered }), makeEnv());
    assert.equal(badToken.status, 401);
    assert.equal((await responseJson(badToken)).code, "invalid_token");

    const expiredToken = await worker.fetch(makeRequest("/unsubscribe/confirm", { token: expired }), makeEnv());
    assert.equal(expiredToken.status, 401);
    assert.equal((await responseJson(expiredToken)).code, "invalid_token");
  });
  assert.equal(upstreamCalls, 0);
});

test("unsubscribe token verification checks signature and expiry", async () => {
  const token = await __test.createUnsubscribeToken(SECRET, "reader@example.com", 1_000);
  assert.deepEqual(await __test.verifyUnsubscribeToken(SECRET, token, 1_001), {
    ok: true,
    email: "reader@example.com",
  });
  assert.deepEqual(await __test.verifyUnsubscribeToken(SECRET, token, 1_000 + __test.TOKEN_TTL_SECONDS), { ok: false });
  assert.deepEqual(await __test.verifyUnsubscribeToken(`${SECRET}-wrong`, token, 1_001), { ok: false });
});

test("unsubscribe confirmation issuance is throttled by caller as well as email", async () => {
  const limiter = makeLimiter([true, false]);
  let upstreamCalls = 0;
  const response = await withMockFetch(async () => {
    upstreamCalls += 1;
    throw new Error("rate limit should run first");
  }, () => worker.fetch(
    makeRequest("/unsubscribe", { email: "reader@example.com", language: "en" }),
    makeEnv({ UNSUBSCRIBE_RATE_LIMITER: limiter }),
  ));

  assert.equal(response.status, 429);
  assert.equal((await responseJson(response)).code, "rate_limited");
  assert.equal(response.headers.get("Retry-After"), "60");
  assert.equal(limiter.calls.length, 2);
  assert.notEqual(limiter.calls[0].key, limiter.calls[1].key);
  assert.equal(upstreamCalls, 0);
});

test("subscribe is throttled before Buttondown", async () => {
  const limiter = makeLimiter([false]);
  let upstreamCalls = 0;
  const response = await withMockFetch(async () => {
    upstreamCalls += 1;
    throw new Error("rate limit should run first");
  }, () => worker.fetch(
    makeRequest("/subscribe", { email: "reader@example.com" }),
    makeEnv({ SUBSCRIBE_RATE_LIMITER: limiter }),
  ));

  assert.equal(response.status, 429);
  assert.equal((await responseJson(response)).code, "rate_limited");
  assert.equal(upstreamCalls, 0);
});

test("Buttondown subscription errors return structured CORS JSON", async () => {
  const response = await withMockFetch(async (url) => {
    assert.match(String(url), /api\.buttondown\.com/);
    return Response.json({ detail: "upstream unavailable" }, { status: 503 });
  }, () => worker.fetch(
    makeRequest("/subscribe", { email: "reader@example.com", language: "en" }),
    makeEnv(),
  ));

  assert.equal(response.status, 502);
  assert.equal((await responseJson(response)).code, "subscription_failed");
});

test("Resend confirmation errors return structured CORS JSON", async () => {
  const calls = [];
  const response = await withMockFetch(async (url, init) => {
    calls.push({ url: String(url), init });
    if (String(url).includes("api.buttondown.com")) {
      return Response.json({ email_address: "reader@example.com", type: "regular" });
    }
    if (String(url).includes("api.resend.com")) return Response.json({ message: "failure" }, { status: 500 });
    throw new Error("unexpected upstream");
  }, () => worker.fetch(
    makeRequest("/unsubscribe", { email: "reader@example.com", language: "ja" }),
    makeEnv(),
  ));

  assert.equal(response.status, 502);
  assert.equal((await responseJson(response)).code, "confirmation_email_failed");
  assert.equal(calls.length, 2);
});

test("confirmation issuance emails a fragment token and returns generic 202", async () => {
  let resendPayload;
  let buttondownMethod;
  const response = await withMockFetch(async (url, init) => {
    if (String(url).includes("api.buttondown.com")) {
      buttondownMethod = init.method;
      return Response.json({ email_address: "reader@example.com", type: "regular" });
    }
    resendPayload = JSON.parse(init.body);
    return Response.json({ id: "email-test" });
  }, () => worker.fetch(
    makeRequest("/unsubscribe", { email: "reader@example.com", language: "en" }),
    makeEnv(),
  ));

  assert.equal(response.status, 202);
  assert.deepEqual(await responseJson(response), { ok: true, status: "confirmation_sent" });
  assert.equal(buttondownMethod, "GET");
  assert.match(resendPayload.html, /unsubscribe\.html#token=/);
  assert.doesNotMatch(resendPayload.html, /unsubscribe\.html\?token=/);
});

test("confirmed unsubscribe preserves history with PATCH and never DELETE", async () => {
  const token = await __test.createUnsubscribeToken(SECRET, "reader@example.com");
  const calls = [];
  const response = await withMockFetch(async (url, init) => {
    calls.push({ url: String(url), init });
    return Response.json({ email_address: "reader@example.com", type: "unsubscribed" });
  }, () => worker.fetch(
    makeRequest("/unsubscribe/confirm", { token }),
    makeEnv(),
  ));

  assert.equal(response.status, 200);
  assert.deepEqual(await responseJson(response), { ok: true });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.method, "PATCH");
  assert.deepEqual(JSON.parse(calls[0].init.body), { type: "unsubscribed" });
  assert.ok(!calls.some((call) => call.init.method === "DELETE"));
});

test("missing secrets and rate-limit bindings fail closed before external calls", async () => {
  let upstreamCalls = 0;
  await withMockFetch(async () => {
    upstreamCalls += 1;
    throw new Error("unexpected external call");
  }, async () => {
    const missingSubscribeLimiter = makeEnv({ SUBSCRIBE_RATE_LIMITER: undefined });
    const subscribe = await worker.fetch(makeRequest("/subscribe", { email: "reader@example.com" }), missingSubscribeLimiter);
    assert.equal(subscribe.status, 503);
    assert.equal((await responseJson(subscribe)).code, "configuration_error");

    const missingTokenSecret = makeEnv({ UNSUBSCRIBE_TOKEN_SECRET: undefined });
    const unsubscribe = await worker.fetch(makeRequest("/unsubscribe", { email: "reader@example.com" }), missingTokenSecret);
    assert.equal(unsubscribe.status, 503);
    assert.equal((await responseJson(unsubscribe)).code, "configuration_error");

    const token = await __test.createUnsubscribeToken(SECRET, "reader@example.com");
    const missingButtondown = makeEnv({ BUTTONDOWN_API_KEY: undefined });
    const confirm = await worker.fetch(makeRequest("/unsubscribe/confirm", { token }), missingButtondown);
    assert.equal(confirm.status, 503);
    assert.equal((await responseJson(confirm)).code, "configuration_error");
  });
  assert.equal(upstreamCalls, 0);
});

test("missing edge client identity fails closed before rate limiting or upstream calls", async () => {
  const limiter = makeLimiter();
  let upstreamCalls = 0;
  const response = await withMockFetch(async () => {
    upstreamCalls += 1;
    throw new Error("unexpected external call");
  }, () => worker.fetch(
    makeRequest("/unsubscribe", { email: "reader@example.com" }, { "CF-Connecting-IP": "" }),
    makeEnv({ UNSUBSCRIBE_RATE_LIMITER: limiter }),
  ));
  assert.equal(response.status, 503);
  assert.equal((await responseJson(response)).code, "client_identity_unavailable");
  assert.equal(limiter.calls.length, 0);
  assert.equal(upstreamCalls, 0);
});
