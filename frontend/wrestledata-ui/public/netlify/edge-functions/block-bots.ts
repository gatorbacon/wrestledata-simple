// Returns a tiny 403 to scrapers before any file is served, to save bandwidth.
// Registered in the repo-root netlify.toml. Keep minimal: no logging.
// A blocked request still counts as a Netlify web request; it just skips the bandwidth.
//
// AI answer engines (ChatGPT search / ChatGPT browsing, Perplexity) may read
// PAGES so they can cite MatSavant (TJ, 2026-10-07; docs/matsavant_seo_plan.md),
// but only from the IP ranges each company publishes -- a scraper that merely
// claims to be ChatGPT still gets the 403 -- and never /data/ or the search
// index (the bulk JSON is what the 2026-09 scraper burst pulled). Their AI
// training crawlers (GPTBot etc.) stay blocked.

import type { Context } from "https://edge.netlify.com";

// Search engines and link-preview bots. Checked first, so they are never blocked.
const ALLOW = [
  "googlebot",
  "bingbot",
  "duckduckbot",
  "facebookexternalhit",
  "twitterbot",
];

// Answer bots: user-agent token -> the company's published IP list.
const ANSWER_BOTS: Record<string, string> = {
  "oai-searchbot": "https://openai.com/searchbot.json",
  "chatgpt-user": "https://openai.com/chatgpt-user.json",
  "perplexitybot": "https://www.perplexity.ai/perplexitybot.json",
  "perplexity-user": "https://www.perplexity.ai/perplexity-user.json",
};

// Same list as robots.txt, plus generic HTTP-library / headless signatures.
const BLOCK = [
  "gptbot", "claudebot", "claude-web", "anthropic-ai",
  "ccbot", "bytespider", "amazonbot", "meta-externalagent", "facebookbot",
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

export function answerBot(userAgent: string | null): string | null {
  const ua = (userAgent ?? "").toLowerCase();
  return Object.keys(ANSWER_BOTS).find((k) => ua.includes(k)) ?? null;
}

// ---- IP ranges ----

type Range = { v6: boolean; base: bigint; bits: number };

function ipToBig(ip: string): { v6: boolean; n: bigint } | null {
  if (ip.includes(".") && !ip.includes(":")) {
    const p = ip.split(".").map(Number);
    if (p.length !== 4 || p.some((x) => !(x >= 0 && x <= 255))) return null;
    return { v6: false, n: BigInt(((p[0] << 24) >>> 0) + (p[1] << 16) + (p[2] << 8) + p[3]) };
  }
  if (ip.startsWith("::ffff:") && ip.includes(".")) return ipToBig(ip.slice(7)); // IPv4-mapped
  const [head, tail = ""] = ip.split("::");
  const h = head ? head.split(":") : [];
  const t = tail ? tail.split(":") : [];
  if (!ip.includes("::") && h.length !== 8) return null;
  const groups = [...h, ...Array(8 - h.length - t.length).fill("0"), ...t];
  if (groups.length !== 8) return null;
  let n = 0n;
  for (const g of groups) {
    const v = parseInt(g || "0", 16);
    if (!(v >= 0 && v <= 0xffff)) return null;
    n = (n << 16n) + BigInt(v);
  }
  return { v6: true, n };
}

function parseRange(cidr: string): Range | null {
  const [ip, bitsStr] = cidr.split("/");
  const a = ipToBig(ip);
  if (!a) return null;
  const width = a.v6 ? 128 : 32;
  const bits = bitsStr === undefined ? width : Number(bitsStr);
  if (!(bits >= 0 && bits <= width)) return null;
  return { v6: a.v6, base: a.n >> BigInt(width - bits), bits };
}

function inRanges(ip: string, ranges: Range[]): boolean {
  const a = ipToBig(ip);
  if (!a) return false;
  const width = a.v6 ? 128 : 32;
  return ranges.some((r) => r.v6 === a.v6 && (a.n >> BigInt(width - r.bits)) === r.base);
}

// Lists are fetched once per edge instance and kept for an hour.
const rangeCache: Record<string, { at: number; ranges: Range[] }> = {};
async function rangesFor(listUrl: string): Promise<Range[]> {
  const hit = rangeCache[listUrl];
  if (hit && Date.now() - hit.at < 3_600_000) return hit.ranges;
  const res = await fetch(listUrl, { headers: { "user-agent": "MatSavant-Edge/1.0" } });
  if (!res.ok) throw new Error(`IP list ${listUrl}: HTTP ${res.status}`);
  const body = await res.json();
  const ranges = (body.prefixes || [])
    .map((p: Record<string, string>) => parseRange(p.ipv4Prefix || p.ipv6Prefix || ""))
    .filter(Boolean) as Range[];
  rangeCache[listUrl] = { at: Date.now(), ranges };
  return ranges;
}

const forbidden = () => new Response("Forbidden", { status: 403 });

export default async (request: Request, context: Context) => {
  const ua = request.headers.get("user-agent");
  const bot = answerBot(ua);
  if (bot) {
    const path = new URL(request.url).pathname;
    if (path.startsWith("/data/") || path === "/search_index.js") return forbidden();
    try {
      if (!inRanges(context.ip, await rangesFor(ANSWER_BOTS[bot]))) return forbidden();
    } catch {
      return forbidden(); // list unavailable: fail closed
    }
    return context.next();
  }
  if (isBlocked(ua)) return forbidden();
  return context.next();
};
