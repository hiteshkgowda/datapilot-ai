"use client";

import { useCallback, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Upload, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useUploadDataset } from "@/hooks/use-datasets";

const ACCEPTED_EXTENSIONS = [".csv", ".xlsx", ".xls"];
const ACCEPTED_MIME = [
  "text/csv",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
];

function isAccepted(file: File): boolean {
  if (ACCEPTED_MIME.includes(file.type)) return true;
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
}

export function UploadZone() {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { mutate, isPending, isSuccess, isError } = useUploadDataset();
  const shouldReduceMotion = useReducedMotion();

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const file = files[0];
      if (!isAccepted(file)) {
        toast.error("Unsupported file type. Upload a CSV or Excel file.");
        return;
      }
      mutate(file);
    },
    [mutate]
  );

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const onDragLeave = useCallback(() => setIsDragging(false), []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  return (
    <motion.div
      animate={
        shouldReduceMotion
          ? {}
          : isDragging
          ? { scale: 1.01 }
          : { scale: 1 }
      }
      transition={{ duration: 0.15 }}
    >
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload dataset — drop CSV or Excel file here"
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => !isPending && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        className={cn(
          "relative flex flex-col items-center justify-center gap-3",
          "rounded-xl border-2 border-dashed px-6 py-10 text-center",
          "cursor-pointer transition-all duration-200 select-none",
          isDragging
            ? "border-primary bg-primary/10 shadow-inner shadow-primary/10"
            : "border-border/60 bg-card/30 hover:border-primary/40 hover:bg-primary/5",
          isPending && "pointer-events-none opacity-70"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="sr-only"
          aria-hidden="true"
          tabIndex={-1}
          onChange={(e) => handleFiles(e.target.files)}
        />

        {/* Icon */}
        <div
          className={cn(
            "flex h-12 w-12 items-center justify-center rounded-full",
            "border border-border/60 bg-muted/40",
            isDragging && "border-primary/40 bg-primary/10"
          )}
        >
          {isPending ? (
            <Loader2 className="h-5 w-5 text-primary animate-spin" />
          ) : isSuccess ? (
            <CheckCircle2 className="h-5 w-5 text-[hsl(var(--success))]" />
          ) : isError ? (
            <XCircle className="h-5 w-5 text-destructive" />
          ) : (
            <Upload
              className={cn(
                "h-5 w-5 transition-colors",
                isDragging ? "text-primary" : "text-muted-foreground"
              )}
            />
          )}
        </div>

        {/* Text */}
        <div>
          <p className="text-sm font-medium text-foreground">
            {isPending
              ? "Uploading…"
              : isDragging
              ? "Drop to upload"
              : "Drop a CSV or Excel file here"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {isPending ? "Please wait" : "or click to browse · .csv, .xlsx, .xls"}
          </p>
        </div>
      </div>
    </motion.div>
  );
}
