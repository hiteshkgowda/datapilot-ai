"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { generateReport, listReports } from "@/lib/api/reports";
import type { ReportMetadata } from "@/lib/api/types";

export function useReports() {
  return useQuery({
    queryKey: ["reports"],
    queryFn: listReports,
    staleTime: 10_000,
  });
}

export function useGenerateReport() {
  const qc = useQueryClient();

  return useMutation<
    ReportMetadata,
    Error,
    { datasetId: string; questions: string[] }
  >({
    mutationFn: ({ datasetId, questions }) => generateReport(datasetId, questions),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["reports"] });
      toast.success("Report generated", {
        description: `${data.dataset_filename} · ${data.deterministic_section_count + data.ai_section_count} sections`,
      });
    },
    onError: (err) => {
      toast.error("Report generation failed", { description: err.message });
    },
  });
}
