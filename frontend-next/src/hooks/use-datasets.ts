"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";
import {
  getDatasetPreview,
  listDatasets,
  uploadDataset,
  ApiError,
} from "@/lib/api/datasets";

export const datasetKeys = {
  all: ["datasets"] as const,
  preview: (id: string) => ["datasets", id, "preview"] as const,
};

export function useDatasets() {
  return useQuery({
    queryKey: datasetKeys.all,
    queryFn: listDatasets,
    staleTime: 30_000,
  });
}

export function useDatasetPreview(id: string, limit = 10) {
  return useQuery({
    queryKey: datasetKeys.preview(id),
    queryFn: () => getDatasetPreview(id, limit),
    staleTime: 5 * 60_000,
    enabled: Boolean(id),
  });
}

export function useUploadDataset() {
  const client = useQueryClient();

  return useMutation({
    mutationFn: uploadDataset,
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: datasetKeys.all });
      toast.success(`"${data.dataset.filename}" uploaded successfully.`);
    },
    onError: (err: unknown) => {
      const message =
        err instanceof ApiError ? err.message : "Upload failed. Please try again.";
      toast.error(message);
    },
  });
}
