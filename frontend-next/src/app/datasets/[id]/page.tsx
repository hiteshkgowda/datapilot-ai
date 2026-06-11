import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { DatasetDetailView } from "@/components/datasets/DatasetDetailView";

export const metadata: Metadata = { title: "Dataset" };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function DatasetDetailPage({ params }: Props) {
  const { id } = await params;

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto">
        <DatasetDetailView id={id} />
      </div>
    </AppShell>
  );
}
