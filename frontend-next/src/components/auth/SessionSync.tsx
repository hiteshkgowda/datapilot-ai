"use client";

import { useEffect } from "react";
import { useSession } from "next-auth/react";
import { setAuthToken } from "@/lib/auth-token";

export function SessionSync() {
  const { data: session } = useSession();

  useEffect(() => {
    setAuthToken(session?.backendToken);
  }, [session?.backendToken]);

  return null;
}
