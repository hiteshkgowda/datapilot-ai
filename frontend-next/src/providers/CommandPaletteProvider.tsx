"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  type Dispatch,
  type SetStateAction,
} from "react";

interface CommandPaletteCtx {
  open: boolean;
  setOpen: Dispatch<SetStateAction<boolean>>;
}

const Ctx = createContext<CommandPaletteCtx | null>(null);

export function CommandPaletteProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return <Ctx.Provider value={{ open, setOpen }}>{children}</Ctx.Provider>;
}

export function useCommandPalette(): CommandPaletteCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCommandPalette must be inside CommandPaletteProvider");
  return ctx;
}
