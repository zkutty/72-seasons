const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "https://ko-72.com",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

function bdRequest(env, path, method = "GET", body = null) {
  const opts = {
    method,
    headers: {
      Authorization: `Token ${env.BUTTONDOWN_API_KEY}`,
      "Content-Type": "application/json",
    },
  };
  if (body) opts.body = JSON.stringify(body);
  return fetch(`https://api.buttondown.email/v1${path}`, opts);
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const url = new URL(request.url);

    // POST /subscribe
    if (url.pathname === "/subscribe" && request.method === "POST") {
      let email;
      try {
        ({ email } = await request.json());
      } catch {
        return json({ error: "Invalid JSON" }, 400);
      }
      if (!email || !email.includes("@")) {
        return json({ error: "Invalid email" }, 400);
      }
      const res = await bdRequest(env, "/subscribers", "POST", { email });
      if (res.ok || res.status === 409) {
        // 409 = already subscribed, treat as success
        return json({ ok: true });
      }
      return json({ error: "Subscription failed" }, 500);
    }

    // POST /unsubscribe
    if (url.pathname === "/unsubscribe" && request.method === "POST") {
      let email;
      try {
        ({ email } = await request.json());
      } catch {
        return json({ error: "Invalid JSON" }, 400);
      }
      const listRes = await bdRequest(env, `/subscribers?email=${encodeURIComponent(email)}`);
      const data = await listRes.json();
      const subscriber = data.results?.[0];
      if (subscriber) {
        await bdRequest(env, `/subscribers/${subscriber.id}`, "DELETE");
      }
      return json({ ok: true });
    }

    return json({ error: "Not found" }, 404);
  },
};
