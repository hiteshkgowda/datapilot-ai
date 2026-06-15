import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { AnalysisWorkspace } from "@/components/analysis/AnalysisWorkspace";

export const metadata: Metadata = { title: "Analysis" };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function AnalysisPage({ params }: Props) {
  const { id } = await params;

  return (
    <AppShell>
      <AnalysisWorkspace datasetId={id} />
    </AppShell>
  );
}
