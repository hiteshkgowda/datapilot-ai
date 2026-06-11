"use client";

import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { runForecast } from "@/lib/api/forecast";
import type { ForecastResponse } from "@/lib/api/types";

interface ForecastVariables {
  datasetId: string;
  question: string;
}

export function useForecast() {
  return useMutation<ForecastResponse, Error, ForecastVariables>({
    mutationFn: ({ datasetId, question }) =>
      runForecast({ dataset_id: datasetId, question }),
    onError: (err) => {
      toast.error("Forecast failed", { description: err.message });
    },
  });
}
