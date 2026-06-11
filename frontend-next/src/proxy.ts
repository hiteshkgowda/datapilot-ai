import { withAuth } from "next-auth/middleware";

// Named variable so Turbopack can statically confirm this is a middleware function.
const proxy = withAuth({ pages: { signIn: "/auth/signin" } });
export default proxy;

export const config = {
  matcher: [
    /*
     * Protect every route except:
     *  - /auth/* (sign-in page)
     *  - /api/auth/* (NextAuth endpoints)
     *  - /_next/* (Next.js internals)
     *  - /favicon.ico, static files
     */
    "/((?!auth/|api/auth/|_next/|favicon\\.ico).*)",
  ],
};
