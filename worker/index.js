import seasonsData from "../data/seasons.json" with { type: "json" };

const ALLOWED_ORIGINS = new Set(["https://ko-72.com"]);
const BUTTONDOWN_API_VERSION = "2026-04-01";
const MAX_JSON_BYTES = 4096;
const TOKEN_TTL_SECONDS = 30 * 60;
const MAX_CLOCK_SKEW_SECONDS = 60;
const encoder = new TextEncoder();

function corsHeaders(request) {
  const origin = request.headers.get("Origin");
  return {
    ...(origin === null || ALLOWED_ORIGINS.has(origin)
      ? { "Access-Control-Allow-Origin": origin ?? "https://ko-72.com" }
      : {}),
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function json(request, body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...corsHeaders(request),
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...extraHeaders,
    },
  });
}

function structuredLog(level, event, details = {}) {
  const payload = JSON.stringify({ event, ...details });
  if (level === "error") console.error(payload);
  else if (level === "warn") console.warn(payload);
  else console.log(payload);
}

function errorType(error) {
  return error instanceof Error ? error.name : typeof error;
}

function normalizeEmail(value) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

function isValidEmail(email) {
  if (!email || email.length > 254) return false;
  const separator = email.lastIndexOf("@");
  if (separator <= 0 || separator !== email.indexOf("@")) return false;
  const local = email.slice(0, separator);
  const domain = email.slice(separator + 1);
  if (local.length > 64 || domain.length > 253) return false;
  if (local.startsWith(".") || local.endsWith(".") || local.includes("..")) return false;
  if (!/^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+$/i.test(local)) return false;
  const labels = domain.split(".");
  if (labels.length < 2) return false;
  return labels.every(
    (label) =>
      label.length > 0 &&
      label.length <= 63 &&
      /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/i.test(label),
  );
}

async function readJsonObject(request) {
  const contentType = request.headers.get("Content-Type")?.split(";", 1)[0].trim().toLowerCase();
  if (contentType !== "application/json") {
    return { ok: false, status: 415, code: "unsupported_media_type", error: "Content-Type must be application/json" };
  }

  const declaredLength = Number(request.headers.get("Content-Length"));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_JSON_BYTES) {
    return { ok: false, status: 413, code: "payload_too_large", error: "Request body is too large" };
  }
  if (!request.body) {
    return { ok: false, status: 400, code: "invalid_json", error: "Invalid JSON" };
  }

  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_JSON_BYTES) {
      await reader.cancel();
      return { ok: false, status: 413, code: "payload_too_large", error: "Request body is too large" };
    }
    chunks.push(value);
  }

  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    const value = JSON.parse(new TextDecoder().decode(bytes));
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new TypeError("Expected object");
    return { ok: true, value };
  } catch {
    return { ok: false, status: 400, code: "invalid_json", error: "Invalid JSON" };
  }
}

function configurationReady(env, required) {
  return required.every((name) => {
    const value = env?.[name];
    if (name.endsWith("_RATE_LIMITER")) return value && typeof value.limit === "function";
    if (name === "UNSUBSCRIBE_TOKEN_SECRET") return typeof value === "string" && value.length >= 32;
    return typeof value === "string" && value.trim().length > 0;
  });
}

async function rateLimitKey(scope, email) {
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(`${scope}\0${email}`));
  return bytesToBase64Url(new Uint8Array(digest));
}

async function enforceRateLimit(request, limiter, scope, email) {
  try {
    const outcome = await limiter.limit({ key: await rateLimitKey(scope, email) });
    if (!outcome?.success) {
      return json(request, { error: "Too many requests", code: "rate_limited" }, 429, { "Retry-After": "60" });
    }
    return null;
  } catch (error) {
    structuredLog("error", "rate_limit_failed", { scope, errorType: errorType(error) });
    return json(request, { error: "Service temporarily unavailable", code: "rate_limit_unavailable" }, 503);
  }
}

async function enforceAbuseLimits(request, limiter, scope, email) {
  const clientIp = request.headers.get("CF-Connecting-IP");
  if (!clientIp) {
    // Cloudflare supplies this header at the edge. Failing closed prevents a
    // caller from bypassing the aggregate limiter if that invariant changes.
    return json(request, { error: "Client identity is unavailable", code: "client_identity_unavailable" }, 503);
  }
  const emailLimited = await enforceRateLimit(request, limiter, `${scope}:email`, email);
  if (emailLimited) return emailLimited;
  // This aggregate check bounds address rotation. The quota is deliberately
  // small, so users behind a shared NAT may share it and receive a 429.
  return enforceRateLimit(request, limiter, `${scope}:client`, clientIp);
}

function bytesToBase64Url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/u, "");
}

function base64UrlToBytes(value) {
  if (!/^[A-Za-z0-9_-]+$/u.test(value)) throw new TypeError("Invalid base64url");
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function importTokenKey(secret) {
  return crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

async function createUnsubscribeToken(secret, email, nowSeconds = Math.floor(Date.now() / 1000)) {
  const payload = {
    v: 1,
    purpose: "unsubscribe",
    email,
    iat: nowSeconds,
    exp: nowSeconds + TOKEN_TTL_SECONDS,
    nonce: crypto.randomUUID(),
  };
  const encodedPayload = bytesToBase64Url(encoder.encode(JSON.stringify(payload)));
  const signature = await crypto.subtle.sign("HMAC", await importTokenKey(secret), encoder.encode(encodedPayload));
  return `${encodedPayload}.${bytesToBase64Url(new Uint8Array(signature))}`;
}

async function verifyUnsubscribeToken(secret, token, nowSeconds = Math.floor(Date.now() / 1000)) {
  if (typeof token !== "string" || token.length > 2048) return { ok: false };
  const parts = token.split(".");
  if (parts.length !== 2) return { ok: false };

  try {
    const [encodedPayload, encodedSignature] = parts;
    const signature = base64UrlToBytes(encodedSignature);
    const verified = await crypto.subtle.verify(
      "HMAC",
      await importTokenKey(secret),
      signature,
      encoder.encode(encodedPayload),
    );
    if (!verified) return { ok: false };

    const payloadBytes = base64UrlToBytes(encodedPayload);
    if (bytesToBase64Url(payloadBytes) !== encodedPayload) return { ok: false };
    const payload = JSON.parse(new TextDecoder().decode(payloadBytes));
    const email = normalizeEmail(payload.email);
    const claimsValid =
      payload.v === 1 &&
      payload.purpose === "unsubscribe" &&
      payload.email === email &&
      isValidEmail(email) &&
      Number.isInteger(payload.iat) &&
      Number.isInteger(payload.exp) &&
      payload.iat <= nowSeconds + MAX_CLOCK_SKEW_SECONDS &&
      payload.exp > nowSeconds &&
      payload.exp > payload.iat &&
      payload.exp - payload.iat <= TOKEN_TTL_SECONDS &&
      typeof payload.nonce === "string" &&
      payload.nonce.length >= 16 &&
      payload.nonce.length <= 64;
    return claimsValid ? { ok: true, email } : { ok: false };
  } catch {
    return { ok: false };
  }
}

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

function bdRequest(env, path, method = "GET", body = null) {
  const opts = {
    method,
    headers: {
      Authorization: `Token ${env.BUTTONDOWN_API_KEY}`,
      "Content-Type": "application/json",
      "X-API-Version": BUTTONDOWN_API_VERSION,
    },
  };
  if (body !== null) opts.body = JSON.stringify(body);
  return fetch(`https://api.buttondown.com/v1${path}`, opts);
}

async function parseUpstreamJson(response) {
  try {
    const value = await response.json();
    return value && typeof value === "object" ? value : {};
  } catch {
    return {};
  }
}

async function getSubscriber(env, email) {
  const response = await bdRequest(env, `/subscribers/${encodeURIComponent(email)}`);
  if (response.status === 404) return { ok: true, subscriber: null };
  if (!response.ok) return { ok: false, status: response.status };
  const subscriber = await parseUpstreamJson(response);
  if (normalizeEmail(subscriber.email_address) !== email || typeof subscriber.type !== "string") {
    return { ok: false, status: 502 };
  }
  return { ok: true, subscriber };
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

function getSeasonEndMetadata(season, year = new Date().getUTCFullYear()) {
  const seasons = seasonsData.seasons;
  const idx = seasons.findIndex((candidate) => candidate.id === season.id);
  if (idx === -1) throw new RangeError(`Unknown season id: ${season.id}`);

  const next = idx < seasons.length - 1 ? seasons[idx + 1] : seasons[0];
  const rollsIntoNextYear =
    next.start_month < season.start_month ||
    (next.start_month === season.start_month && next.start_day <= season.start_day);
  const nextYear = year + (rollsIntoNextYear ? 1 : 0);
  const start = new Date(Date.UTC(year, season.start_month - 1, season.start_day));
  const nextStart = new Date(Date.UTC(nextYear, next.start_month - 1, next.start_day));
  const end = new Date(nextStart.getTime() - 86400000);

  return {
    endMonth: end.getUTCMonth() + 1,
    endDay: end.getUTCDate(),
    duration: Math.round((end.getTime() - start.getTime()) / 86400000) + 1,
  };
}

function getSeasonDateRange(season) {
  const { endMonth, endDay, duration } = getSeasonEndMetadata(season);
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
  const { endMonth, endDay, duration } = getSeasonEndMetadata(season);
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
  const season = findActiveSeason(new Date());
  if (!season) return { ok: false, status: 500 };

  const copy = WELCOME_COPY[lang] || WELCOME_COPY[DEFAULT_LANG];
  return sendResendEmail(env, {
    from: "Kō <seasons@ko-72.com>",
    to: [email],
    subject: copy.subject(season),
    html: renderWelcomeEmail(season, lang),
  }, "welcome_email_failed");
}

async function sendResendEmail(env, payload, failureEvent) {
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    structuredLog("error", failureEvent, { upstreamStatus: response.status });
    return { ok: false, status: response.status };
  }
  return { ok: true };
}

async function sendUnsubscribeConfirmation(env, email, lang, token) {
  // Keep the bearer token in the URL fragment so it is not sent to the static
  // site host in the HTTP request or leaked in referrer headers.
  const confirmationUrl = `${unsubscribeUrl(lang)}#token=${encodeURIComponent(token)}`;
  const content = lang === "ja"
    ? {
        subject: "Kō（候）· 配信停止の確認",
        heading: "配信停止の確認",
        body: "Kō の配信停止リクエストを受け付けました。下のリンクを開き、配信停止を確定してください。このリンクは30分間有効です。",
        action: "配信停止を確認",
        ignore: "このリクエストに心当たりがない場合は、このメールを無視してください。",
      }
    : {
        subject: "Kō · Confirm your unsubscribe request",
        heading: "Confirm your unsubscribe request",
        body: "We received a request to unsubscribe this address from Kō. Open the link below and confirm within 30 minutes.",
        action: "Review unsubscribe request",
        ignore: "If you did not request this, you can safely ignore this email.",
      };
  const html = `<!doctype html><html lang="${lang}"><body style="margin:0;padding:32px;background:#e8e5de;color:#2c2c2a;font-family:system-ui,-apple-system,sans-serif"><div style="max-width:560px;margin:auto;background:#f5f3ee;padding:36px"><p style="font-family:Georgia,serif;font-size:22px">Kō <span style="font-size:14px;color:#888780">候</span></p><h1 style="font-family:Georgia,serif;font-size:22px;font-weight:400">${content.heading}</h1><p style="line-height:1.7">${content.body}</p><p style="margin:28px 0"><a href="${confirmationUrl}" style="display:inline-block;background:#2c2c2a;color:#f5f3ee;text-decoration:none;padding:12px 20px">${content.action}</a></p><p style="color:#888780;font-size:13px;line-height:1.7">${content.ignore}</p></div></body></html>`;
  return sendResendEmail(env, {
    from: "Kō <seasons@ko-72.com>",
    to: [email],
    subject: content.subject,
    html,
  }, "unsubscribe_confirmation_email_failed");
}

async function reactivateSubscriber(env, email, lang = DEFAULT_LANG) {
  const subscriberResult = await getSubscriber(env, email);
  if (!subscriberResult.ok || !subscriberResult.subscriber) {
    return { ok: false, status: subscriberResult.status ?? 404 };
  }
  const patchResponse = await bdRequest(env, `/subscribers/${encodeURIComponent(email)}`, "PATCH", {
    type: "regular",
    tags: [`lang:${lang}`],
  });
  if (!patchResponse.ok) return { ok: false, status: patchResponse.status };
  return sendWelcomeEmail(env, email, lang);
}

async function handleSubscribe(request, env) {
  const parsed = await readJsonObject(request);
  if (!parsed.ok) return json(request, { error: parsed.error, code: parsed.code }, parsed.status);

  const email = normalizeEmail(parsed.value.email);
  if (!isValidEmail(email)) {
    return json(request, { error: "Invalid email", code: "invalid_email" }, 400);
  }
  if (!configurationReady(env, ["BUTTONDOWN_API_KEY", "RESEND_API_KEY", "SUBSCRIBE_RATE_LIMITER"])) {
    return json(request, { error: "Service is not configured", code: "configuration_error" }, 503);
  }

  const limited = await enforceAbuseLimits(request, env.SUBSCRIBE_RATE_LIMITER, "subscribe", email);
  if (limited) return limited;
  const lang = normalizeLang(parsed.value.language);
  const ipAddress = request.headers.get("CF-Connecting-IP");

  try {
    const response = await bdRequest(env, "/subscribers", "POST", {
      email_address: email,
      type: "regular",
      tags: [`lang:${lang}`],
      ...(ipAddress ? { ip_address: ipAddress } : {}),
    });
    const data = await parseUpstreamJson(response);
    let result;
    if (response.ok) {
      result = await sendWelcomeEmail(env, email, lang);
    } else if (data.code === "email_already_exists") {
      result = await reactivateSubscriber(env, email, lang);
    } else {
      structuredLog("error", "buttondown_subscribe_failed", { upstreamStatus: response.status });
      const status = response.status >= 500 || response.status === 401 || response.status === 403 || response.status === 429 ? 502 : 400;
      return json(request, { error: "Subscription failed", code: "subscription_failed" }, status);
    }

    if (!result.ok) {
      structuredLog("error", "welcome_delivery_failed", { upstreamStatus: result.status });
      return json(request, { error: "Subscription saved, but the welcome email could not be sent", code: "welcome_email_failed" }, 502);
    }
    return json(request, { ok: true });
  } catch (error) {
    structuredLog("error", "subscribe_upstream_unreachable", { errorType: errorType(error) });
    return json(request, { error: "Subscription service unreachable", code: "upstream_unreachable" }, 502);
  }
}

async function handleUnsubscribeRequest(request, env) {
  const parsed = await readJsonObject(request);
  if (!parsed.ok) return json(request, { error: parsed.error, code: parsed.code }, parsed.status);

  const email = normalizeEmail(parsed.value.email);
  if (!isValidEmail(email)) {
    return json(request, { error: "Invalid email", code: "invalid_email" }, 400);
  }
  const required = ["BUTTONDOWN_API_KEY", "RESEND_API_KEY", "UNSUBSCRIBE_TOKEN_SECRET", "UNSUBSCRIBE_RATE_LIMITER"];
  if (!configurationReady(env, required)) {
    return json(request, { error: "Service is not configured", code: "configuration_error" }, 503);
  }

  const limited = await enforceAbuseLimits(request, env.UNSUBSCRIBE_RATE_LIMITER, "unsubscribe_request", email);
  if (limited) return limited;
  const genericAccepted = () => json(request, { ok: true, status: "confirmation_sent" }, 202);

  try {
    const subscriberResult = await getSubscriber(env, email);
    if (!subscriberResult.ok) {
      structuredLog("error", "buttondown_unsubscribe_lookup_failed", { upstreamStatus: subscriberResult.status });
      return json(request, { error: "Unsubscribe service unavailable", code: "upstream_error" }, 502);
    }
    if (!subscriberResult.subscriber || subscriberResult.subscriber.type === "unsubscribed") {
      return genericAccepted();
    }

    const lang = normalizeLang(parsed.value.language);
    const token = await createUnsubscribeToken(env.UNSUBSCRIBE_TOKEN_SECRET, email);
    const delivery = await sendUnsubscribeConfirmation(env, email, lang, token);
    if (!delivery.ok) {
      return json(request, { error: "Confirmation email could not be sent", code: "confirmation_email_failed" }, 502);
    }
    return genericAccepted();
  } catch (error) {
    structuredLog("error", "unsubscribe_request_upstream_unreachable", { errorType: errorType(error) });
    return json(request, { error: "Unsubscribe service unavailable", code: "upstream_unreachable" }, 502);
  }
}

async function handleUnsubscribeConfirm(request, env) {
  const parsed = await readJsonObject(request);
  if (!parsed.ok) return json(request, { error: parsed.error, code: parsed.code }, parsed.status);
  if (!configurationReady(env, ["BUTTONDOWN_API_KEY", "UNSUBSCRIBE_TOKEN_SECRET"])) {
    return json(request, { error: "Service is not configured", code: "configuration_error" }, 503);
  }

  const verification = await verifyUnsubscribeToken(env.UNSUBSCRIBE_TOKEN_SECRET, parsed.value.token);
  if (!verification.ok) {
    return json(request, { error: "Confirmation link is invalid or expired", code: "invalid_token" }, 401);
  }

  try {
    const response = await bdRequest(env, `/subscribers/${encodeURIComponent(verification.email)}`, "PATCH", {
      type: "unsubscribed",
    });
    if (response.status === 404) return json(request, { ok: true });
    if (!response.ok) {
      structuredLog("error", "buttondown_unsubscribe_patch_failed", { upstreamStatus: response.status });
      return json(request, { error: "Unsubscribe service unavailable", code: "upstream_error" }, 502);
    }
    return json(request, { ok: true });
  } catch (error) {
    structuredLog("error", "unsubscribe_confirm_upstream_unreachable", { errorType: errorType(error) });
    return json(request, { error: "Unsubscribe service unavailable", code: "upstream_unreachable" }, 502);
  }
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin");
    if (origin && !ALLOWED_ORIGINS.has(origin)) {
      return json(request, { error: "Origin is not allowed", code: "cors_forbidden" }, 403);
    }

    if (request.method === "OPTIONS") {
      const requestedMethod = request.headers.get("Access-Control-Request-Method");
      if (!origin || requestedMethod !== "POST") {
        return json(request, { error: "Invalid preflight request", code: "invalid_preflight" }, 403);
      }
      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }

    const path = new URL(request.url).pathname;
    const knownPaths = new Set(["/subscribe", "/unsubscribe", "/unsubscribe/confirm"]);
    if (knownPaths.has(path) && request.method !== "POST") {
      return json(request, { error: "Method not allowed", code: "method_not_allowed" }, 405, { Allow: "POST, OPTIONS" });
    }

    try {
      if (path === "/subscribe") return await handleSubscribe(request, env);
      if (path === "/unsubscribe") return await handleUnsubscribeRequest(request, env);
      if (path === "/unsubscribe/confirm") return await handleUnsubscribeConfirm(request, env);
      return json(request, { error: "Not found", code: "not_found" }, 404);
    } catch (error) {
      structuredLog("error", "unhandled_request_error", { path, errorType: errorType(error) });
      return json(request, { error: "Internal server error", code: "internal_error" }, 500);
    }
  },
};

export const __test = {
  createUnsubscribeToken,
  verifyUnsubscribeToken,
  getSeasonDateRange,
  getSeasonDateRangeForLang,
  isValidEmail,
  normalizeEmail,
  TOKEN_TTL_SECONDS,
};
