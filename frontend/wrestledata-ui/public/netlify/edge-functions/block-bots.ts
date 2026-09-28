// Returns a tiny 403 to scrapers before any file is served, to save bandwidth.
// Registered in the repo-root netlify.toml. Keep minimal: no logging, no external calls.
// A blocked request still counts as a Netlify web request; it just skips the bandwidth.

import type { Context } from "https://edge.netlify.com";

// Search engines and link-preview bots. Checked first, so they are never blocked.
const ALLOW = [
  "googlebot",
  "bingbot",
  "duckduckbot",
  "facebookexternalhit",
  "twitterbot",
];

// Same list as robots.txt, plus generic HTTP-library / headless signatures.
const BLOCK = [
  "gptbot", "chatgpt-user", "oai-searchbot", "claudebot", "claude-web", "anthropic-ai",
  "ccbot", "bytespider", "amazonbot", "meta-externalagent", "facebookbot", "perplexitybot",
  "google-extended", "applebot-extended", "cohere-ai", "diffbot", "imagesiftbot",
  "timpibot", "omgilibot", "ahrefsbot", "semrushbot", "mj12bot", "dotbot", "petalbot",
  "blexbot", "dataforseobot", "seznambot", "yandexbot",
  "python-requests", "python-urllib", "aiohttp", "scrapy", "go-http-client", "curl",
  "wget", "httpclient", "java/", "okhttp", "headlesschrome", "phantomjs",
];

export function isBlocked(userAgent: string | null): boolean {
  const ua = (userAgent ?? "").trim().toLowerCase();
  if (!ua) return true;
  // Plain Applebot is allowed; Applebot-Extended (AI training) is not.
  if (ua.includes("applebot") && !ua.includes("applebot-extended")) return false;
  if (ALLOW.some((s) => ua.includes(s))) return false;
  return BLOCK.some((s) => ua.includes(s));
}

export default async (request: Request, context: Context) => {
  if (isBlocked(request.headers.get("user-agent"))) {
    return new Response("Forbidden", { status: 403 });
  }
  return context.next();
};
