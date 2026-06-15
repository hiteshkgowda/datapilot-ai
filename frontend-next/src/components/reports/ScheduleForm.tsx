"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useCreateSchedule, useUpdateSchedule } from "@/hooks/use-scheduled-reports";
import type {
  DatasetMetadata,
  ScheduledReport,
  ScheduledReportCreate,
  ScheduleFrequency,
} from "@/lib/api/types";

const DOW_OPTIONS = [
  { value: 0, label: "Monday" },
  { value: 1, label: "Tuesday" },
  { value: 2, label: "Wednesday" },
  { value: 3, label: "Thursday" },
  { value: 4, label: "Friday" },
  { value: 5, label: "Saturday" },
  { value: 6, label: "Sunday" },
];

interface Props {
  datasets: DatasetMetadata[];
  editing?: ScheduledReport | null;
  onDone: () => void;
}

export function ScheduleForm({ datasets, editing, onDone }: Props) {
  const create = useCreateSchedule();
  const update = useUpdateSchedule();
  const busy = create.isPending || update.isPending;

  const [datasetId, setDatasetId] = useState(editing?.dataset_id ?? "");
  const [frequency, setFrequency] = useState<ScheduleFrequency>(
    editing?.frequency ?? "daily"
  );
  const [hour, setHour] = useState(editing?.hour ?? 8);
  const [dow, setDow] = useState(editing?.day_of_week ?? 0);
  const [dom, setDom] = useState(editing?.day_of_month ?? 1);
  const [enabled, setEnabled] = useState(editing?.enabled ?? true);
  const [questions, setQuestions] = useState(
    editing?.questions.join("\n") ?? ""
  );

  function buildBody(): ScheduledReportCreate {
    return {
      dataset_id: datasetId,
      frequency,
      hour,
      day_of_week: frequency === "weekly" ? dow : undefined,
      day_of_month: frequency === "monthly" ? dom : undefined,
      questions: questions
        .split("\n")
        .map((q) => q.trim())
        .filter(Boolean),
      enabled,
    };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!datasetId) return;
    if (editing) {
      await update.mutateAsync({ id: editing.schedule_id, body: buildBody() });
    } else {
      await create.mutateAsync(buildBody());
    }
    onDone();
  }

  const labelCls = "block text-xs font-medium text-muted-foreground mb-1";
  const inputCls =
    "w-full rounded-lg border border-border/50 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";
  const selectCls = inputCls;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Dataset */}
      <div>
        <label className={labelCls}>Dataset</label>
        <select
          required
          value={datasetId}
          onChange={(e) => setDatasetId(e.target.value)}
          className={selectCls}
        >
          <option value="">Select a dataset…</option>
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {d.filename}
            </option>
          ))}
        </select>
      </div>

      {/* Frequency */}
      <div>
        <label className={labelCls}>Frequency</label>
        <select
          value={frequency}
          onChange={(e) => setFrequency(e.target.value as ScheduleFrequency)}
          className={selectCls}
        >
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </div>

      {/* Day of week — weekly only */}
      {frequency === "weekly" && (
        <div>
          <label className={labelCls}>Day of week</label>
          <select
            value={dow}
            onChange={(e) => setDow(Number(e.target.value))}
            className={selectCls}
          >
            {DOW_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Day of month — monthly only */}
      {frequency === "monthly" && (
        <div>
          <label className={labelCls}>Day of month (1–28)</label>
          <input
            type="number"
            min={1}
            max={28}
            value={dom}
            onChange={(e) => setDom(Number(e.target.value))}
            className={inputCls}
          />
        </div>
      )}

      {/* Hour */}
      <div>
        <label className={labelCls}>Hour (UTC, 0–23)</label>
        <input
          type="number"
          min={0}
          max={23}
          value={hour}
          onChange={(e) => setHour(Number(e.target.value))}
          className={inputCls}
        />
      </div>

      {/* Optional questions */}
      <div>
        <label className={labelCls}>
          Optional questions (one per line — adds AI sections to the report)
        </label>
        <textarea
          rows={3}
          value={questions}
          onChange={(e) => setQuestions(e.target.value)}
          placeholder="e.g. What were the top 5 products by revenue?"
          className={`${inputCls} resize-none`}
        />
      </div>

      {/* Enabled toggle */}
      <div className="flex items-center gap-2">
        <input
          id="enabled"
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="h-4 w-4 accent-primary"
        />
        <label htmlFor="enabled" className="text-sm text-foreground">
          Active
        </label>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="ghost" onClick={onDone} disabled={busy}>
          Cancel
        </Button>
        <Button type="submit" disabled={busy || !datasetId}>
          {busy ? "Saving…" : editing ? "Update schedule" : "Create schedule"}
        </Button>
      </div>
    </form>
  );
}
