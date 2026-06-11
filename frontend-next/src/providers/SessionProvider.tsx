"use client";

import { SessionProvider as NextAuthSessionProvider } from "next-auth/react";
import { SessionSync } from "@/components/auth/SessionSync";

export function SessionProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextAuthSessionProvider>
      <SessionSync />
      {children}
    </NextAuthSessionProvider>
  );
}
