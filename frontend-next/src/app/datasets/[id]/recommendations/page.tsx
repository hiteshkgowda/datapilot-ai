import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { RecommendationWorkspace } from "@/components/recommendations/RecommendationWorkspace";

export const metadata: Metadata = { title: "Recommendations" };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function RecommendationsPage({ params }: Props) {
  const { id } = await params;

  return (
    <AppShell mainClassName="overflow-hidden p-0">
      <RecommendationWorkspace datasetId={id} />
    </AppShell>
  );
}
