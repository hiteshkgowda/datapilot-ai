"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  createConnection,
  deleteConnection,
  listConnections,
  listTables,
  registerTable,
  testConnection,
} from "@/lib/api/connections";
import type {
  ConnectionCreate,
  ConnectionTestResult,
  DatasetMetadata,
  RegisterTableRequest,
} from "@/lib/api/types";

export function useConnections() {
  return useQuery({
    queryKey: ["connections"],
    queryFn: listConnections,
    staleTime: 30_000,
  });
}

export function useCreateConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (request: ConnectionCreate) => createConnection(request),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      toast.success("Connection saved", { description: data.name });
    },
    onError: (err: Error) => {
      toast.error("Failed to save connection", { description: err.message });
    },
  });
}

export function useDeleteConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteConnection(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      toast.success("Connection deleted");
    },
    onError: (err: Error) => {
      toast.error("Failed to delete connection", { description: err.message });
    },
  });
}

export function useTestConnection() {
  return useMutation<ConnectionTestResult, Error, string>({
    mutationFn: (id: string) => testConnection(id),
  });
}

export function useListTables(connectionId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["tables", connectionId],
    queryFn: () => listTables(connectionId),
    enabled,
    staleTime: 60_000,
  });
}

export function useRegisterTable(connectionId: string) {
  const qc = useQueryClient();
  return useMutation<DatasetMetadata, Error, RegisterTableRequest>({
    mutationFn: (request) => registerTable(connectionId, request),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      toast.success("Table registered as dataset", {
        description: data.filename,
        action: {
          label: "View",
          onClick: () => {
            window.location.href = `/datasets/${data.id}`;
          },
        },
      });
    },
    onError: (err: Error) => {
      toast.error("Failed to register table", { description: err.message });
    },
  });
}
