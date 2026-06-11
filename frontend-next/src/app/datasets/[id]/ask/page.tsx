import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { AskWorkspace } from "@/components/ask/AskWorkspace";

export const metadata: Metadata = { title: "Ask Data" };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function AskPage({ params }: Props) {
  const { id } = await params;

  return (
    // Disable the default scrolling main and padding — the chat workspace
    // manages its own internal scroll for the conversation thread.
    <AppShell mainClassName="overflow-hidden p-0">
      <AskWorkspace datasetId={id} />
    </AppShell>
  );
}
