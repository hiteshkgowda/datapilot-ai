"use client";

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "uda-sidebar-collapsed";

export function useSidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);

  // Read persisted preference after mount to avoid SSR mismatch
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null) setCollapsed(stored === "true");
    setMounted(true);
  }, []);

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, String(next));
      return next;
    });
  }, []);

  const expand = useCallback(() => {
    setCollapsed(false);
    localStorage.setItem(STORAGE_KEY, "false");
  }, []);

  const collapse = useCallback(() => {
    setCollapsed(true);
    localStorage.setItem(STORAGE_KEY, "true");
  }, []);

  return { collapsed, toggle, expand, collapse, mounted };
}
