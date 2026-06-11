"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  executeCrud,
  getAuditLog,
  previewCrud,
  rollbackCrud,
} from "@/lib/api/crud";
import type {
  CrudExecuteRequest,
  CrudRequest,
  RollbackRequest,
} from "@/lib/api/types";

export function useCrudPreview() {
  return useMutation({
    mutationFn: (request: CrudRequest) => previewCrud(request),
    onError: (err: Error) => {
      toast.error("Preview failed", { description: err.message });
    },
  });
}

export function useCrudExecute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (request: CrudExecuteRequest) => executeCrud(request),
    onSuccess: (data) => {
      // Invalidate audit log so it refreshes after a successful execute
      qc.invalidateQueries({ queryKey: ["crud-audit"] });
      toast.success(`${data.operation} completed`, {
        description: `${data.affected_rows} row(s) affected on ${data.table_name}`,
      });
    },
    onError: (err: Error) => {
      toast.error("Execution failed", { description: err.message });
    },
  });
}

export function useCrudRollback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (request: RollbackRequest) => rollbackCrud(request),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["crud-audit"] });
      toast.success("Rollback complete", {
        description: `${data.restored_rows} row(s) restored`,
      });
    },
    onError: (err: Error) => {
      toast.error("Rollback failed", { description: err.message });
    },
  });
}

export function useCrudAudit(connectionId: string | null) {
  return useQuery({
    queryKey: ["crud-audit", connectionId],
    queryFn: () => getAuditLog(connectionId!),
    enabled: !!connectionId,
    staleTime: 15_000,
  });
}
