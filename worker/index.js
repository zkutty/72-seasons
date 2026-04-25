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

const SUPPORTED_LANGS = new Set(["en", "ja"]);
const DEFAULT_LANG = "en";

function normalizeLang(value) {
  const v = (value || "").toString().toLowerCase().trim();
  return SUPPORTED_LANGS.has(v) ? v : DEFAULT_LANG;
}

function siteUrl(lang) {
  return lang === "ja" ? "https://ko-72.com/ja" : "https://ko-72.com";
}

function archiveUrl(season, lang) {
  const file = `${String(season.id).padStart(2, "0")}-${season.slug}.html`;
  return `${siteUrl(lang)}/archive/${file}`;
}

function unsubscribeUrl(lang) {
  return `${siteUrl(lang)}/unsubscribe.html`;
}
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

function getSeasonDateRange(season) {
  const seasons = seasonsData.seasons;
  const idx = seasons.findIndex((s) => s.id === season.id);
  const next = idx < seasons.length - 1 ? seasons[idx + 1] : seasons[0];
  const year = new Date().getUTCFullYear();
  const nextYear = idx < seasons.length - 1 ? year : year + 1;
  const nextStart = new Date(Date.UTC(nextYear, next.start_month - 1, next.start_day));
  const end = new Date(nextStart - 86400000); // day before next season
  const endMonth = end.getUTCMonth() + 1;
  const endDay = end.getUTCDate();
  const duration = Math.round((end - new Date(Date.UTC(year, season.start_month - 1, season.start_day))) / 86400000) + 1;
  return {
    dateRange: `${MONTHS_SHORT[season.start_month]} ${season.start_day} – ${MONTHS_SHORT[endMonth]} ${endDay}`,
    duration,
  };
}

const WELCOME_COPY = {
  en: {
    preheader: "Welcome to Kō · 72 micro-seasons of the year",
    welcomeKicker: "Welcome",
    welcomeHeading: "Thank you for subscribing.",
    intro: "Kō follows the 72 <em>shichijūni-kō</em> — Japan's traditional micro-seasons, each just five days long. Every five days you'll receive a short letter: what is blooming, what is on the table, a cultural note, and a haiku.",
    rightNow: "Right now",
    cta: "Read the current letter →",
    footerNote: "Your next letter arrives when the season turns.",
    archive: "Archive",
    unsubscribe: "Unsubscribe",
    subject: (season) => `Welcome to Kō · ${season.name_en}`,
    seasonName: (season) => escapeHtml(season.name_en),
    seasonAlt: (season) => `${escapeHtml(season.name_romaji)} &nbsp;·&nbsp; <span style="font-family:'Hiragino Mincho ProN','Yu Mincho','MS Mincho',serif;">${escapeHtml(season.name_jp)}</span>`,
    metaPrefix: (season, dateRange, duration) => `${capitalize(season.major_season)} · Micro-season ${String(season.id).padStart(2, "0")} of 72 · ${dateRange} · ${duration} days`,
    serif: "Georgia,'Times New Roman',serif",
  },
  ja: {
    preheader: "Kō（候）へようこそ · 一年の七十二候",
    welcomeKicker: "ようこそ",
    welcomeHeading: "ご登録ありがとうございます。",
    intro: "Kō は、日本の伝統的な暦の五日ごとの微小な季節 — <em>七十二候</em> — をひとつずつお届けします。五日に一度、短い便りが届きます：今咲くもの、食卓のもの、文化の一節、そして俳句を。",
    rightNow: "今",
    cta: "今号を読む →",
    footerNote: "次の便りは、季節が変わる日に届きます。",
    archive: "アーカイブ",
    unsubscribe: "配信停止",
    subject: (season) => `Kō（候）へようこそ · ${season.name_jp}`,
    seasonName: (season) => `<span style="font-family:'Hiragino Mincho ProN','Yu Mincho','MS Mincho',serif;">${escapeHtml(season.name_jp)}</span>`,
    seasonAlt: (season) => `${escapeHtml(season.name_romaji)} &nbsp;·&nbsp; ${escapeHtml(season.name_en)}`,
    metaPrefix: (season, dateRange, duration) => `${majorSeasonJa(season.major_season)} · 七十二候 第${String(season.id).padStart(2, "0")}番 · ${dateRange} · ${duration}日間`,
    serif: "'Hiragino Mincho ProN','Yu Mincho','MS Mincho',Georgia,serif",
  },
};

const MAJOR_SEASON_JA = { spring: "春", summer: "夏", autumn: "秋", winter: "冬" };
function majorSeasonJa(name) { return MAJOR_SEASON_JA[name] || name; }

function getSeasonDateRangeForLang(season, lang) {
  const seasons = seasonsData.seasons;
  const idx = seasons.findIndex((s) => s.id === season.id);
  const next = idx < seasons.length - 1 ? seasons[idx + 1] : seasons[0];
  const year = new Date().getUTCFullYear();
  const nextYear = idx < seasons.length - 1 ? year : year + 1;
  const nextStart = new Date(Date.UTC(nextYear, next.start_month - 1, next.start_day));
  const end = new Date(nextStart - 86400000);
  const endMonth = end.getUTCMonth() + 1;
  const endDay = end.getUTCDate();
  const duration = Math.round((end - new Date(Date.UTC(year, season.start_month - 1, season.start_day))) / 86400000) + 1;
  const dateRange = lang === "ja"
    ? `${season.start_month}月${season.start_day}日 – ${endMonth}月${endDay}日`
    : `${MONTHS_SHORT[season.start_month]} ${season.start_day} – ${MONTHS_SHORT[endMonth]} ${endDay}`;
  return { dateRange, duration };
}

function renderWelcomeEmail(season, lang = DEFAULT_LANG) {
  const copy = WELCOME_COPY[lang] || WELCOME_COPY[DEFAULT_LANG];
  const accent = ACCENT_COLORS[season.major_season] || "#888780";
  const archiveLink = archiveUrl(season, lang);
  const archiveIndex = `${siteUrl(lang)}/archive/`;
  const unsubscribeLink = unsubscribeUrl(lang);
  const { dateRange, duration } = getSeasonDateRangeForLang(season, lang);

  return `<!DOCTYPE html>
<html lang="${lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Welcome to Kō</title>
</head>
<body style="margin:0;padding:0;background-color:#e8e5de;">
<span style="display:none;font-size:1px;color:#e8e5de;max-height:0;max-width:0;opacity:0;overflow:hidden;">${copy.preheader}</span>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#e8e5de;">
  <tr>
    <td align="center" style="padding:40px 16px;">
      <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;">

        <tr>
          <td style="background-color:#1a1a18;padding:32px 36px 28px 36px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td><span style="font-family:${copy.serif};font-size:22px;font-weight:400;color:#f5f3ee;letter-spacing:0.02em;">Kō</span><span style="font-family:system-ui,-apple-system,sans-serif;font-size:14px;color:#888780;margin-left:10px;">候</span></td></tr>
            </table>
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:20px 0 0 0;">
              <tr><td style="border-top:1px solid #333330;font-size:0;line-height:0;">&nbsp;</td></tr>
            </table>
            <p style="margin:20px 0 14px 0;font-family:system-ui,-apple-system,sans-serif;font-size:11px;font-weight:500;letter-spacing:0.1em;text-transform:uppercase;color:${accent};">${copy.welcomeKicker}</p>
            <p style="margin:0;font-family:${copy.serif};font-size:26px;font-weight:400;letter-spacing:-0.01em;color:#f5f3ee;line-height:1.3;">${copy.welcomeHeading}</p>
          </td>
        </tr>

        <tr>
          <td style="background-color:#f5f3ee;padding:36px 36px 8px 36px;">
            <p style="margin:0;font-family:${copy.serif};font-size:17px;line-height:1.9;color:#2c2c2a;">${copy.intro}</p>
          </td>
        </tr>

        <tr>
          <td style="background-color:#f5f3ee;padding:28px 36px 0 36px;">
            <p style="margin:0 0 12px 0;font-family:system-ui,-apple-system,sans-serif;font-size:11px;font-weight:500;letter-spacing:0.1em;text-transform:uppercase;color:#888780;">${copy.rightNow}</p>
          </td>
        </tr>

        <tr>
          <td style="background-color:#f5f3ee;padding:0 36px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#edeae3;border-top:2px solid ${accent};">
              <tr>
                <td style="padding:20px 24px;">
                  <p style="margin:0 0 6px 0;font-family:system-ui,-apple-system,sans-serif;font-size:11px;font-weight:500;letter-spacing:0.1em;text-transform:uppercase;color:${accent};">${copy.metaPrefix(season, dateRange, duration)}</p>
                  <p style="margin:0 0 4px 0;font-family:${copy.serif};font-size:22px;color:#2c2c2a;line-height:1.3;">${copy.seasonName(season)}</p>
                  <p style="margin:0;font-family:system-ui,-apple-system,sans-serif;font-size:13px;color:#888780;letter-spacing:0.02em;">${copy.seasonAlt(season)}</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <td style="background-color:#f5f3ee;padding:28px 36px 0 36px;text-align:center;">
            <a href="${archiveLink}" style="display:inline-block;font-family:system-ui,-apple-system,sans-serif;font-size:13px;letter-spacing:0.08em;text-transform:uppercase;color:#f5f3ee;background-color:#1a1a18;text-decoration:none;padding:12px 24px;">${copy.cta}</a>
          </td>
        </tr>

        <tr>
          <td style="background-color:#f5f3ee;padding:28px 36px 36px 36px;text-align:center;">
            <p style="margin:0;font-family:system-ui,-apple-system,sans-serif;font-size:13px;line-height:1.7;color:#888780;">${copy.footerNote}</p>
          </td>
        </tr>

        <tr>
          <td style="background-color:#e8e5de;padding:22px 36px;border-top:1px solid #d8d5ce;">
            <p style="margin:0;font-family:system-ui,-apple-system,sans-serif;font-size:11px;color:#888780;text-align:center;letter-spacing:0.04em;">
              <a href="${archiveIndex}" style="color:#888780;text-decoration:none;">${copy.archive}</a>
              &nbsp;·&nbsp;
              <a href="${unsubscribeLink}" style="color:#888780;text-decoration:none;">${copy.unsubscribe}</a>
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

async function sendWelcomeEmail(env, email, lang = DEFAULT_LANG) {
  if (!env.RESEND_API_KEY) {
    console.warn("RESEND_API_KEY not set — skipping welcome email");
    return;
  }
  const season = findActiveSeason(new Date());
  if (!season) return;

  const copy = WELCOME_COPY[lang] || WELCOME_COPY[DEFAULT_LANG];
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: "Kō <seasons@ko-72.com>",
      to: [email],
      subject: copy.subject(season),
      html: renderWelcomeEmail(season, lang),
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    console.error(`Welcome email failed (${res.status}): ${body}`);
  }
}

async function reactivateSubscriber(env, email, lang = DEFAULT_LANG) {
  try {
    const listRes = await bdRequest(env, `/subscribers?email=${encodeURIComponent(email)}`);
    if (!listRes.ok) {
      console.error(`Reactivate lookup failed (${listRes.status}) for ${email}`);
      return;
    }
    const listData = await listRes.json();
    const subscriber = listData.results?.[0];
    if (!subscriber) return;
    const patchBody = { type: "regular", tags: [`lang:${lang}`] };
    const patchRes = await bdRequest(env, `/subscribers/${subscriber.id}`, "PATCH", patchBody);
    if (!patchRes.ok) {
      const body = await patchRes.text();
      console.error(`Reactivate PATCH failed (${patchRes.status}) for ${email}: ${body}`);
      return;
    }
    await sendWelcomeEmail(env, email, lang);
  } catch (err) {
    console.error(`Reactivation failed for ${email}: ${err.message}`);
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
      let email, language;
      try {
        ({ email, language } = await request.json());
      } catch {
        return json({ error: "Invalid JSON" }, 400);
      }
      if (!email || !email.includes("@")) {
        return json({ error: "Invalid email" }, 400);
      }
      const lang = normalizeLang(language);
      let res, data;
      try {
        res = await bdRequest(env, "/subscribers", "POST", {
          email_address: email,
          type: "regular",
          tags: [`lang:${lang}`],
        });
        data = await res.json().catch(() => ({}));
      } catch (err) {
        console.error(`Subscribe request failed for ${email}: ${err.message}`);
        return json({ error: "Subscription service unreachable" }, 502);
      }
      if (res.ok) {
        ctx.waitUntil(sendWelcomeEmail(env, email, lang));
        return json({ ok: true });
      }
      if (data.code === "email_already_exists") {
        ctx.waitUntil(reactivateSubscriber(env, email, lang));
        return json({ ok: true });
      }
      console.error(`Buttondown subscribe failed (${res.status}) for ${email}:`, JSON.stringify(data));
      const status = res.status >= 500 ? 502 : 400;
      return json({ error: data.detail ?? "Subscription failed" }, status);
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
