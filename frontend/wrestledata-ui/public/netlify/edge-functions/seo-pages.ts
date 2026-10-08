// Wrestler and team pages for search engines and link previews
// (docs/matsavant_seo_plan.md Step 3):
//   - /wrestler/<slug>, /team/<slug>: writes the page's own title, description,
//     canonical and share tags into the HTML, plus the name (and the wrestler's
//     season line) as real text, so crawlers that don't run JavaScript
//     (ChatGPT, Perplexity, link previews) see the page, not an empty shell.
//   - /wrestler.html?id=<season id>, /team.html?team=<id>, old team ids,
//     uppercase / trailing-slash variants: 301 to the one official address.
//   - unknown wrestler / team: the normal page with a 404 status and noindex.
// Titles and descriptions come from /seo_text.js -- the same file the pages
// use -- so the raw HTML and the page after it loads always agree. Lookups read
// /seo/* (small files from scripts/seo/build_url_slugs.py), never /data/*, so
// they don't count against the per-IP data rate limit.
// Any error -> the normal static page (onError: "bypass"), whose JS handles
// the name-based address itself.

import type { Config, Context } from "https://edge.netlify.com";
import "../../seo_text.js";

// deno-lint-ignore no-explicit-any
const SEO = (globalThis as any).MatSavantSEO;

// block-bots.ts 403s requests without a user agent; our own lookups send one.
const OWN = { headers: { "user-agent": "MatSavant-Edge/1.0" } };

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const ID_RE = /^\d{1,15}$/;

// deno-lint-ignore no-explicit-any
async function getJSON(path: string, base: URL): Promise<any> {
  const res = await fetch(new URL(path, base), OWN);
  return res.ok ? res.json() : null;
}

// /seo/teams.json is ~80 entries and only changes on deploy (a new deploy
// starts fresh edge instances), so keep it per instance for 10 minutes.
// deno-lint-ignore no-explicit-any
let teamsCache: { at: number; data: any } | null = null;
async function teamsList(base: URL) {
  if (!teamsCache || Date.now() - teamsCache.at > 600_000) {
    teamsCache = { at: Date.now(), data: (await getJSON("/seo/teams.json", base)) || {} };
  }
  return teamsCache.data;
}

const esc = (s: unknown) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

// JSON inside <script type="application/json">: can never close the tag.
const LS = new RegExp(String.fromCharCode(0x2028), "g"), PS = new RegExp(String.fromCharCode(0x2029), "g");
const scriptJSON = (obj: unknown) =>
  JSON.stringify(obj).replace(/</g, "\\u003c").replace(LS, "\\u2028").replace(PS, "\\u2029");

function headTags(o: { title: string; description?: string; canonical?: string; type?: string; noindex?: boolean }) {
  const t = [`<title>${esc(o.title)}</title>`];
  if (o.noindex) t.push(`<meta name="robots" content="noindex">`);
  if (o.description) t.push(`<meta name="description" content="${esc(o.description)}">`);
  if (o.canonical) t.push(`<link rel="canonical" href="${esc(o.canonical)}">`);
  if (!o.noindex) {
    t.push(
      `<meta property="og:site_name" content="MatSavant">`,
      `<meta property="og:type" content="${o.type || "website"}">`,
      `<meta property="og:title" content="${esc(o.title)}">`,
    );
    if (o.description) t.push(`<meta property="og:description" content="${esc(o.description)}">`);
    if (o.canonical) t.push(`<meta property="og:url" content="${esc(o.canonical)}">`);
    t.push(`<meta name="twitter:card" content="summary">`);
  }
  return t.join("\n  ");
}

// Replaces what sits between the <!--EDGE:HEAD--> markers (the static <title>).
// Missing markers -> page unchanged (never throw over a template change).
function setHead(html: string, tags: string) {
  return html.replace(/<!--EDGE:HEAD-->[\s\S]*?<!--\/EDGE:HEAD-->/, `<!--EDGE:HEAD-->${tags}<!--/EDGE:HEAD-->`);
}

// Fills an empty element written exactly as `id="x"></tag>` in the page; skipped if not found.
function fill(html: string, id: string, text: string) {
  return html.replace(new RegExp(`(id="${id}"[^>]*>)(</)`), `$1${esc(text)}$2`);
}

const CACHE = {
  "cache-control": "public, max-age=0, must-revalidate",
  // Netlify's CDN keeps the edge result until the next deploy (deploys clear it).
  "netlify-cdn-cache-control": "public, s-maxage=604800",
};

function redirect(location: string, vary?: string) {
  const headers: Record<string, string> = { location, ...CACHE };
  if (vary) headers["netlify-vary"] = vary;
  return new Response(null, { status: 301, headers });
}

function htmlResponse(html: string, original: Response, status: number, vary?: string) {
  const headers = new Headers(original.headers);
  // The static file's validators no longer describe this body.
  for (const h of ["content-length", "etag", "last-modified"]) headers.delete(h);
  for (const [k, v] of Object.entries(CACHE)) headers.set(k, v);
  if (vary) headers.set("netlify-vary", vary);
  return new Response(html, { status, headers });
}

async function staticPage(context: Context) {
  const res = await context.next();
  const ok = res.status === 200 && (res.headers.get("content-type") || "").includes("text/html");
  return { res, html: ok ? await res.text() : null };
}

// ---------------------------------------------------------------- wrestlers

async function wrestlerBySlug(url: URL, context: Context, segment: string) {
  const vary = "query=season|view";
  const slug = segment.toLowerCase();
  if (slug !== segment || url.pathname.endsWith("/")) return redirect(`/wrestler/${slug}${url.search}`, vary);
  const info = SLUG_RE.test(slug) ? await getJSON(`/seo/wrestlers/${slug}.json`, url) : null;
  if (info?.alias_of) return redirect(`/wrestler/${info.alias_of}${url.search}`, vary);

  const { res, html } = await staticPage(context);
  if (html === null) return res;
  if (!info) {
    return htmlResponse(setHead(html, headTags({ title: "Wrestler Not Found | MatSavant", noindex: true })), res, 404, vary);
  }

  const canonical = SEO.SITE + SEO.wrestlerPath(slug);
  let out = setHead(html, headTags({
    title: SEO.wrestlerTitle(info),
    description: SEO.wrestlerDescription(info),
    canonical,
    type: "profile",
  }));
  out = fill(out, "wrestler-name", info.name);
  out = fill(out, "wp2m-name", info.name);
  // The desktop season line, built exactly as app.js renderHeader() builds it
  // ("2026: 26-0, #1 at 174"), only for the latest season the page opens on.
  const season = url.searchParams.get("season");
  if (!season || season === String(info.latest_season)) {
    const parts = [`${info.latest_season}:`];
    if (info.season_record) parts.push(info.season_record + (info.season_record.includes(",") ? "" : ","));
    if (info.rank && info.weight) parts.push(`#${info.rank} at ${info.weight}`);
    out = fill(out, "wrestler-resume", parts.join(" "));
  }
  // app.js reads this instead of fetching /seo/wrestlers/<slug>.json again.
  out = out.replace("</body>", `<script id="wrestler-slug-data" type="application/json">${scriptJSON(info)}</script>\n</body>`);
  return htmlResponse(out, res, 200, vary);
}

async function wrestlerById(url: URL, context: Context) {
  const id = url.searchParams.get("id") || "";
  if (!ID_RE.test(id)) return context.next(); // the page says "No wrestler selected"
  const shard = await getJSON(`/seo/by_id/${Number(id) % 97}.json`, url);
  const hit = shard?.[id];
  if (!hit) {
    const { res, html } = await staticPage(context);
    if (html === null) return res;
    return htmlResponse(setHead(html, headTags({ title: "Wrestler Not Found | MatSavant", noindex: true })), res, 404, "query=id");
  }
  const [slug, season] = hit;
  // Always name the season: Netlify appends the request's own query string to
  // any redirect whose target has none (seen on the 2026-10-07 preview:
  // ?id=X -> /wrestler/levi-haines?id=X), and it leaves targets that have one
  // alone. ?season= is also exactly the season the old link pointed at. The
  // page's canonical stays the bare /wrestler/<slug>.
  const q = new URLSearchParams({ season: String(season) });
  const view = url.searchParams.get("view");
  if (view) q.set("view", view);
  return redirect(`/wrestler/${slug}?${q}`, "query=id|view");
}

// ---------------------------------------------------------------- teams

async function teamBySlug(url: URL, context: Context, segment: string) {
  const id = SEO.teamIdFromPath(segment);
  const official = SEO.teamPath(id); // applies old-id aliases
  if (official !== url.pathname) return redirect(official);

  const teams = await teamsList(url);
  const team = teams[id];
  const { res, html } = await staticPage(context);
  if (html === null) return res;
  if (!team) {
    return htmlResponse(setHead(html, headTags({ title: "Team Not Found | MatSavant", noindex: true })), res, 404);
  }
  let out = setHead(html, headTags({
    title: SEO.teamTitle(team.name, team.season),
    description: SEO.teamDescription(team.name, team.season),
    canonical: SEO.SITE + official,
  }));
  out = fill(out, "team-name", team.name);
  return htmlResponse(out, res, 200);
}

// ---------------------------------------------------------------- entry

export default async (request: Request, context: Context) => {
  if (request.method !== "GET" && request.method !== "HEAD") return context.next();
  const url = new URL(request.url);
  const path = url.pathname;

  let m = path.match(/^\/wrestler\/([^/]+)\/?$/);
  if (m) return wrestlerBySlug(url, context, decodeURIComponent(m[1]));
  if (path === "/wrestler.html" || path === "/wrestler") return wrestlerById(url, context);

  m = path.match(/^\/team\/([^/]+)\/?$/);
  if (m) return teamBySlug(url, context, decodeURIComponent(m[1]));
  if (path === "/team.html" || path === "/team") {
    const team = url.searchParams.get("team");
    // Netlify re-appends ?team=<old> to this target (see wrestlerById); harmless --
    // the page reads the path, and its canonical is the clean /team/<name>.
    return team && /^[a-z0-9_&-]+$/i.test(team) ? redirect(SEO.teamPath(team.toLowerCase())) : context.next();
  }
  return context.next();
};

export const config: Config = {
  path: ["/wrestler", "/wrestler.html", "/wrestler/*", "/team", "/team.html", "/team/*"],
  onError: "bypass",
  cache: "manual",
};
