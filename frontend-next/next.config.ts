import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

// Read at build/start time so the CSP reflects the actual backend origin.
// Falls back to localhost for local development.
const backendOrigin =
  (process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000").replace(
    /\/$/,
    ""
  );

// ---------------------------------------------------------------------------
// Content-Security-Policy
//
// Rationale for each directive:
//
//  script-src  'unsafe-inline'  — Next.js App Router embeds inline bootstrap
//                                  scripts for hydration and chunk loading.
//  script-src  'unsafe-eval'    — Plotly uses `new Function()` internally for
//                                  expression parsing in some chart types.
//  style-src   'unsafe-inline'  — Framer Motion applies animation values as
//                                  inline `style` attributes; Plotly also injects
//                                  inline styles into chart SVG elements.
//  img-src     data: blob:      — Plotly chart-to-image export (data URI) and
//                                  file-download helper (blob URL).
//  font-src    'self'           — next/font/google downloads fonts at build time
//                                  and self-hosts them; no CDN origin required.
//  connect-src backendOrigin    — fetch/XHR calls to the FastAPI backend.
//              accounts.google.com / oauth2.googleapis.com
//                               — Google OAuth token exchange (NextAuth).
//  frame-src   accounts.google.com
//                               — Google OAuth sign-in flow embedded frame.
//  form-action accounts.google.com
//                               — NextAuth redirects the browser to Google's
//                                  auth endpoint as a form POST.
//  worker-src  blob:            — Plotly WebGL renderer spawns blob: workers.
//  object-src  'none'           — block Flash / legacy plugin vectors.
//  base-uri    'self'           — prevent <base href> injection attacks.
// ---------------------------------------------------------------------------
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self'",
  `connect-src 'self' ${backendOrigin} https://accounts.google.com https://oauth2.googleapis.com`,
  "frame-src 'self' https://accounts.google.com",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self' https://accounts.google.com",
  "worker-src 'self' blob:",
]
  .join("; ")
  // Collapse any accidental double-spaces (e.g. if backendOrigin is empty).
  .replace(/\s+/g, " ")
  .trim();

// ---------------------------------------------------------------------------
// All security response headers
// ---------------------------------------------------------------------------
const securityHeaders = [
  // Prevent MIME-type sniffing — browsers must honour Content-Type.
  { key: "X-Content-Type-Options", value: "nosniff" },

  // Block this app from being embedded in any <iframe> on another origin.
  { key: "X-Frame-Options", value: "DENY" },

  // Only send the origin (no path/query) as Referer when crossing origins.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },

  // Restrict access to hardware APIs this app never uses.
  {
    key: "Permissions-Policy",
    value: [
      "camera=()",
      "microphone=()",
      "geolocation=()",
      "payment=()",
      "usb=()",
      "magnetometer=()",
      "gyroscope=()",
      "accelerometer=()",
    ].join(", "),
  },

  // HSTS: tell browsers to use HTTPS exclusively for 2 years.
  // Omitted in development — setting HSTS on localhost would break plain-HTTP
  // requests for the lifetime of max-age (hard to undo without clearing HSTS).
  ...(isDev
    ? []
    : [
        {
          key: "Strict-Transport-Security",
          value: "max-age=63072000; includeSubDomains; preload",
        },
      ]),

  { key: "Content-Security-Policy", value: csp },
];

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        // Apply to every route — static assets, API routes, pages.
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
