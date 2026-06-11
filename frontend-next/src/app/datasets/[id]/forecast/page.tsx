import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { ForecastWorkspace } from "@/components/forecast/ForecastWorkspace";

export const metadata: Metadata = { title: "Forecast" };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function ForecastPage({ params }: Props) {
  const { id } = await params;

  return (
    <AppShell>
      <ForecastWorkspace datasetId={id} />
    </AppShell>
  );
}
