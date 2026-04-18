import seasonsData from "../data/seasons.json";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "https://ko-72.com",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const ACCENT_COLORS = {
  spring: "#6b8f71",
  summer: "#c9734a",
  autumn: "#d4a853",
  winter: "#4a7fa5",
};

const MONTHS_SHORT = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS_IN_MONTH = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

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

function findActiveSeason(today) {
  const seasons = seasonsData.seasons;
  let best = null;
  let bestTs = -Infinity;
  const year = today.getUTCFullYear();

  for (const s of seasons) {
    const ts = Date.UTC(year, s.start_month - 1, s.start_day);
    if (ts <= today.getTime() && ts > bestTs) {
      best = s;
      bestTs = ts;
    }
  }
  if (best) return best;

  // Fall back to previous year (covers early January)
  for (const s of seasons) {
    const ts = Date.UTC(year - 1, s.start_month - 1, s.start_day);
    if (ts > bestTs) {
      best = s;
      bestTs = ts;
    }
  }
  return best;
}

function renderWelcomeEmail(season) {
  const accent = ACCENT_COLORS[season.major_season] || "#888780";
  const archiveUrl = `https://ko-72.com/archive/${String(season.id).padStart(2, "0")}-${season.slug}.html`;

  let endDay = season.start_day + 4;
  let endMonth = season.start_month;
  if (endDay > DAYS_IN_MONTH[season.start_month]) {
    endDay -= DAYS_IN_MONTH[season.start_month];
    endMonth += 1;
  }
  const dateRange = `${MONTHS_SHORT[season.start_month]} ${season.start_day} → ${MONTHS_SHORT[endMonth]} ${endDay}`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Welcome to Kō</title>
</head>
<body style="margin:0;padding:0;background-color:#e8e5de;">
<span style="display:none;font-size:1px;color:#e8e5de;max-height:0;max-width:0;opacity:0;overflow:hidden;">Welcome to Kō · 72 micro-seasons of the year</span>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#e8e5de;">
  <tr>
    <td align="center" style="padding:40px 16px;">
      <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;">

        <tr>
          <td style="background-color:#1a1a18;padding:32px 36px 28px 36px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td><span style="font-family:Georgia,'Times New Roman',serif;font-size:22px;font-weight:400;color:#f5f3ee;letter-spacing:0.02em;">Kō</span><span style="font-family:system-ui,-apple-system,sans-serif;font-size:14px;color:#888780;margin-left:10px;">候</span></td></tr>
            </table>
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:20px 0 0 0;">
              <tr><td style="border-top:1px solid #333330;font-size:0;line-height:0;">&nbsp;</td></tr>
            </table>
            <p style="margin:20px 0 14px 0;font-family:system-ui,-apple-system,sans-serif;font-size:11px;font-weight:500;letter-spacing:0.1em;text-transform:uppercase;color:${accent};">Welcome</p>
            <p style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:26px;font-weight:400;letter-spacing:-0.01em;color:#f5f3ee;line-height:1.3;">Thank you for subscribing.</p>
          </td>
        </tr>

        <tr>
          <td style="background-color:#f5f3ee;padding:36px 36px 8px 36px;">
            <p style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:17px;line-height:1.9;color:#2c2c2a;">Kō follows the 72 <em>shichijūni-kō</em> — Japan's traditional micro-seasons, each just five days long. Every five days you'll receive a short letter: what is blooming, what is on the table, a cultural note, and a haiku.</p>
          </td>
        </tr>

        <tr>
          <td style="background-color:#f5f3ee;padding:28px 36px 0 36px;">
            <p style="margin:0 0 12px 0;font-family:system-ui,-apple-system,sans-serif;font-size:11px;font-weight:500;letter-spacing:0.1em;text-transform:uppercase;color:#888780;">Right now</p>
          </td>
        </tr>

        <tr>
          <td style="background-color:#f5f3ee;padding:0 36px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#edeae3;border-top:2px solid ${accent};">
              <tr>
                <td style="padding:20px 24px;">
                  <p style="margin:0 0 6px 0;font-family:system-ui,-apple-system,sans-serif;font-size:11px;font-weight:500;letter-spacing:0.1em;text-transform:uppercase;color:${accent};">${capitalize(season.major_season)} · Micro-season ${String(season.id).padStart(2, "0")} of 72 · ${dateRange}</p>
                  <p style="margin:0 0 4px 0;font-family:Georgia,'Times New Roman',serif;font-size:22px;color:#2c2c2a;line-height:1.3;">${escapeHtml(season.name_en)}</p>
                  <p style="margin:0;font-family:system-ui,-apple-system,sans-serif;font-size:13px;color:#888780;letter-spacing:0.02em;">${escapeHtml(season.name_romaji)} &nbsp;·&nbsp; <span style="font-family:'Hiragino Mincho ProN','Yu Mincho','MS Mincho',serif;">${escapeHtml(season.name_jp)}</span></p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <td style="background-color:#f5f3ee;padding:28px 36px 0 36px;text-align:center;">
            <a href="${archiveUrl}" style="display:inline-block;font-family:system-ui,-apple-system,sans-serif;font-size:13px;letter-spacing:0.08em;text-transform:uppercase;color:#f5f3ee;background-color:#1a1a18;text-decoration:none;padding:12px 24px;">Read the current letter →</a>
          </td>
        </tr>

        <tr>
          <td style="background-color:#f5f3ee;padding:28px 36px 36px 36px;text-align:center;">
            <p style="margin:0;font-family:system-ui,-apple-system,sans-serif;font-size:13px;line-height:1.7;color:#888780;">Your next letter arrives when the season turns.</p>
          </td>
        </tr>

        <tr>
          <td style="background-color:#e8e5de;padding:22px 36px;border-top:1px solid #d8d5ce;">
            <p style="margin:0;font-family:system-ui,-apple-system,sans-serif;font-size:11px;color:#888780;text-align:center;letter-spacing:0.04em;">
              <a href="https://ko-72.com/archive/" style="color:#888780;text-decoration:none;">Archive</a>
              &nbsp;·&nbsp;
              <a href="https://ko-72.com/unsubscribe.html" style="color:#888780;text-decoration:none;">Unsubscribe</a>
            </p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>`;
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function sendWelcomeEmail(env, email) {
  if (!env.RESEND_API_KEY) {
    console.warn("RESEND_API_KEY not set — skipping welcome email");
    return;
  }
  const season = findActiveSeason(new Date());
  if (!season) return;

  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: "Kō <seasons@ko-72.com>",
      to: [email],
      subject: `Welcome to Kō · ${season.name_en}`,
      html: renderWelcomeEmail(season),
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    console.error(`Welcome email failed (${res.status}): ${body}`);
  }
}

export default {
  async fetch(request, env, ctx) {
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
      let res, data;
      try {
        res = await bdRequest(env, "/subscribers", "POST", { email_address: email, type: "regular" });
        data = await res.json();
      } catch (err) {
        return json({ error: `Request failed: ${err.message}` }, 500);
      }
      if (res.ok) {
        ctx.waitUntil(sendWelcomeEmail(env, email));
        return json({ ok: true });
      }
      if (data.code === "email_already_exists") {
        return json({ ok: true });
      }
      return json({ error: data.detail ?? "Subscription failed" }, 500);
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
