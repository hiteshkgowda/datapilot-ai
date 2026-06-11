"use client";

import { Toaster } from "sonner";
import { QueryProvider } from "./QueryProvider";
import { ThemeProvider } from "./ThemeProvider";
import { CommandPaletteProvider } from "./CommandPaletteProvider";
import { SessionProvider } from "./SessionProvider";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <ThemeProvider>
        <QueryProvider>
          <CommandPaletteProvider>
            {children}
            <Toaster
              position="bottom-right"
              closeButton
              toastOptions={{
                duration: 4000,
                classNames: {
                  toast:
                    "bg-elevated border border-border text-foreground elevation-md text-sm font-sans",
                  title: "font-medium tracking-tight",
                  description: "text-muted-foreground text-xs",
                  actionButton:
                    "bg-primary text-primary-foreground text-xs font-medium rounded-md",
                  cancelButton:
                    "bg-muted text-muted-foreground text-xs font-medium rounded-md",
                  closeButton:
                    "border border-border bg-muted text-muted-foreground hover:text-foreground rounded-md",
                  error: "!border-destructive/40",
                },
              }}
            />
          </CommandPaletteProvider>
        </QueryProvider>
      </ThemeProvider>
    </SessionProvider>
  );
}
