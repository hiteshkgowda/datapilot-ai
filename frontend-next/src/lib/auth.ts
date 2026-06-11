import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";

// Fail fast in production rather than allowing silent OAuth failures.
if (process.env.NODE_ENV === "production") {
  if (!process.env.GOOGLE_CLIENT_ID) {
    throw new Error(
      "GOOGLE_CLIENT_ID is not set. Add it to your Vercel environment variables."
    );
  }
  if (!process.env.GOOGLE_CLIENT_SECRET) {
    throw new Error(
      "GOOGLE_CLIENT_SECRET is not set. Add it to your Vercel environment variables."
    );
  }
}
import { v4 as uuidv4 } from "uuid";
import * as jose from "jose";

declare module "next-auth" {
  interface Session {
    backendToken?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    backendToken?: string;
  }
}

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
    }),
  ],

  callbacks: {
    async jwt({ token, account }) {
      // Generate a short-lived backend token on first sign-in (account is present)
      // or when the existing one has expired.
      const secret = process.env.BACKEND_JWT_SECRET;
      if (!secret) return token;

      const needsNew =
        account != null ||
        !token.backendToken ||
        _isExpired(token.backendToken);

      if (needsNew) {
        const secretKey = new TextEncoder().encode(secret);
        token.backendToken = await new jose.SignJWT({
          sub: token.sub ?? "",
          email: token.email ?? "",
          name: token.name ?? "",
          jti: uuidv4(),
        })
          .setProtectedHeader({ alg: "HS256" })
          .setIssuer("uda-frontend")
          .setAudience("uda-api")
          .setExpirationTime("15m")
          .sign(secretKey);
      }

      return token;
    },

    async session({ session, token }) {
      session.backendToken = token.backendToken;
      return session;
    },
  },

  pages: {
    signIn: "/auth/signin",
  },
};

function _isExpired(jwt: string): boolean {
  try {
    // Decode without verification — we only need the exp claim here.
    // Signature is verified by the backend on every API call.
    const payload = jose.decodeJwt(jwt);
    if (typeof payload.exp !== "number") return true;
    // Refresh 60 s before actual expiry so API calls don't race the clock.
    return Date.now() / 1000 > payload.exp - 60;
  } catch {
    return true;
  }
}
