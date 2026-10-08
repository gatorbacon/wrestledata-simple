// Per-IP rate limit on the data files (docs/matsavant_seo_plan.md Step 5). The
// function itself does nothing; Netlify enforces the rateLimit rule below
// (429 once an IP passes the cap; enforcement can lag ~10 s). Code-based rules
// are on every plan (Personal: 2 per project); check the deploy log lists it.
//
// Sizing (measured 2026-10-07): the heaviest page is a big team roster, which
// loads every wrestler's profile (Sacred Heart: 67 /data/ requests; Penn State
// 35; home 25; a wrestler page 8). An active visitor uses ~200 in 3 minutes;
// 600 leaves room for several people behind one shared IP (school, carrier).
// It stops fast bursts like the 2026-09-24 scraper (262K requests in a day),
// not a patient scraper under ~3 requests/second -- Cloudflare is the backstop.
// The edge function's own lookups read /seo/, not /data/, so they don't count.

import type { Config, Context } from "https://edge.netlify.com";

export default async (_request: Request, context: Context) => context.next();

export const config: Config = {
  path: "/data/*",
  rateLimit: {
    windowLimit: 600,
    windowSize: 180,
    aggregateBy: ["ip", "domain"],
  },
};
