"use client";

import { useCallback, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  BarChart2,
  CheckCircle2,
  Clock,
  Code2,
  Database,
  Eye,
  FileText,
  GitBranch,
  LineChart,
  Loader2,
  PenLine,
  ShieldAlert,
  TrendingUp,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { PlannedToolCall, ToolResult } from "@/lib/api/types";

// ── Tool metadata (mirrors AgentTimeline) ─────────────────────────────────────

const TOOL_META: Record<
  string,
  { icon: React.ElementType; color: string; bg: string; label: string }
> = {
  dataset_preview: {
    icon: Database, label: "Dataset",
    color: "text-sky-400", bg: "bg-sky-400/15 border-sky-400/30",
  },
  analytics: {
    icon: BarChart2, label: "Analytics",
    color: "text-indigo-400", bg: "bg-indigo-400/15 border-indigo-400/30",
  },
  visualization: {
    icon: LineChart, label: "Viz",
    color: "text-violet-400", bg: "bg-violet-400/15 border-violet-400/30",
  },
  forecast: {
    icon: TrendingUp, label: "Forecast",
    color: "text-emerald-400", bg: "bg-emerald-400/15 border-emerald-400/30",
  },
  report: {
    icon: FileText, label: "Report",
    color: "text-amber-400", bg: "bg-amber-400/15 border-amber-400/30",
  },
  crud_preview: {
    icon: Eye, label: "Preview",
    color: "text-orange-400", bg: "bg-orange-400/15 border-orange-400/30",
  },
  crud_execute: {
    icon: PenLine, label: "Execute",
    color: "text-red-400", bg: "bg-red-400/15 border-red-400/30",
  },
  sql_query: {
    icon: Code2, label: "SQL",
    color: "text-cyan-400", bg: "bg-cyan-400/15 border-cyan-400/30",
  },
};

function fmtMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;
}

// ── Node data shape ───────────────────────────────────────────────────────────

type NodeStatus = "success" | "error" | "pending" | "approval" | "planned";

interface StepNodeData extends Record<string, unknown> {
  toolName: string;
  stepLabel: string;
  status: NodeStatus;
  durationMs: number;
  output: Record<string, unknown>;
  errorMsg: string | null;
  args: Record<string, unknown>;
  index: number;
  isLast: boolean;
}

type StepNode = Node<StepNodeData, "step">;

// ── Custom node component ─────────────────────────────────────────────────────

function StepNodeComponent({ data, selected }: NodeProps<StepNode>) {
  const meta = TOOL_META[data.toolName];
  const Icon = meta?.icon ?? Zap;

  const statusIcon = {
    success: <CheckCircle2 className="h-3 w-3 text-emerald-400" />,
    error: <XCircle className="h-3 w-3 text-red-400" />,
    pending: <Loader2 className="h-3 w-3 text-primary animate-spin" />,
    approval: <ShieldAlert className="h-3 w-3 text-orange-400" />,
    planned: <GitBranch className="h-3 w-3 text-muted-foreground/50" />,
  }[data.status];

  const ringColor = {
    success: "border-emerald-400/40",
    error: "border-red-400/40",
    pending: "border-primary/40",
    approval: "border-orange-400/40",
    planned: "border-border/60",
  }[data.status];

  return (
    <div
      className={cn(
        "relative rounded-xl border bg-card/90 backdrop-blur-sm shadow-lg",
        "transition-all duration-150 cursor-pointer select-none",
        ringColor,
        selected && "ring-2 ring-primary/50 ring-offset-1 ring-offset-background"
      )}
      style={{ width: 260 }}
    >
      {!data.isLast && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="!w-2 !h-2 !border-2 !border-primary/40 !bg-primary/20"
        />
      )}
      {data.index > 0 && (
        <Handle
          type="target"
          position={Position.Top}
          className="!w-2 !h-2 !border-2 !border-primary/40 !bg-primary/20"
        />
      )}

      <div className="flex items-start gap-3 px-3 py-2.5">
        {/* Step number */}
        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-primary/30 bg-primary/10 text-[9px] font-bold text-primary mt-0.5">
          {data.index + 1}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-foreground leading-tight truncate">
            {data.stepLabel}
          </p>
          <div className="flex items-center gap-1.5 mt-1">
            <div
              className={cn(
                "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                meta?.bg ?? "bg-muted/20 border-border/40"
              )}
            >
              <Icon className={cn("h-2.5 w-2.5", meta?.color ?? "text-muted-foreground")} />
            </div>
            <span className={cn("text-[10px] font-mono", meta?.color ?? "text-muted-foreground/60")}>
              {meta?.label ?? data.toolName}
            </span>

            {data.status === "approval" && (
              <span className="text-[9px] font-medium text-orange-400 bg-orange-400/10 border border-orange-400/25 rounded px-1">
                approval
              </span>
            )}
          </div>
        </div>

        {/* Status + duration */}
        <div className="flex flex-col items-end gap-1 shrink-0">
          {statusIcon}
          {data.durationMs > 0 && (
            <span className="text-[9px] text-muted-foreground/50 tabular-nums flex items-center gap-0.5">
              <Clock className="h-2 w-2" />
              {fmtMs(data.durationMs)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

const nodeTypes = { step: StepNodeComponent };

// ── Graph builder ─────────────────────────────────────────────────────────────

const NODE_GAP_Y = 120;
const NODE_X = 0;

function buildFromExecuted(steps: ToolResult[]): { nodes: StepNode[]; edges: Edge[] } {
  const nodes: StepNode[] = steps.map((step, i) => ({
    id: `step-${i}`,
    type: "step" as const,
    position: { x: NODE_X, y: i * NODE_GAP_Y },
    data: {
      toolName: step.tool_name,
      stepLabel: step.step_label,
      status: step.error ? "error" : "success",
      durationMs: step.duration_ms,
      output: step.output,
      errorMsg: step.error ?? null,
      args: {},
      index: i,
      isLast: i === steps.length - 1,
    } satisfies StepNodeData,
  }));

  const edges: Edge[] = steps.slice(0, -1).map((_, i) => ({
    id: `e-${i}`,
    source: `step-${i}`,
    target: `step-${i + 1}`,
    animated: true,
    style: { stroke: "hsl(var(--primary) / 0.35)", strokeWidth: 1.5 },
  }));

  return { nodes, edges };
}

function buildFromPlan(steps: PlannedToolCall[]): { nodes: StepNode[]; edges: Edge[] } {
  const nodes: StepNode[] = steps.map((step, i) => ({
    id: `plan-${i}`,
    type: "step" as const,
    position: { x: NODE_X, y: i * NODE_GAP_Y },
    data: {
      toolName: step.tool_name,
      stepLabel: step.step_label,
      status: step.requires_approval ? "approval" : "planned",
      durationMs: 0,
      output: {},
      errorMsg: null,
      args: step.arguments,
      index: i,
      isLast: i === steps.length - 1,
    } satisfies StepNodeData,
  }));

  const edges: Edge[] = steps.slice(0, -1).map((_, i) => ({
    id: `pe-${i}`,
    source: `plan-${i}`,
    target: `plan-${i + 1}`,
    animated: false,
    style: { stroke: "hsl(var(--border) / 0.6)", strokeWidth: 1.5, strokeDasharray: "4 3" },
  }));

  return { nodes, edges };
}

// ── Detail panel ──────────────────────────────────────────────────────────────

interface DetailPanelProps {
  data: StepNodeData | null;
}

function DetailPanel({ data }: DetailPanelProps) {
  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center gap-3 px-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted/20">
          <GitBranch className="h-4 w-4 text-muted-foreground/30" />
        </div>
        <p className="text-xs text-muted-foreground/50">
          Click a node to inspect inputs and outputs
        </p>
      </div>
    );
  }

  const meta = TOOL_META[data.toolName];
  const Icon = meta?.icon ?? Zap;

  const hasArgs = Object.keys(data.args).length > 0;
  const hasOutput = Object.keys(data.output).length > 0;

  return (
    <div className="flex flex-col h-full overflow-y-auto p-4 gap-4">
      {/* Header */}
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
            meta?.bg ?? "bg-muted/20 border-border/40"
          )}
        >
          <Icon className={cn("h-4 w-4", meta?.color ?? "text-muted-foreground")} />
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground leading-tight">
            {data.stepLabel}
          </p>
          <p className={cn("text-[11px] font-mono mt-0.5", meta?.color ?? "text-muted-foreground/60")}>
            {meta?.label ?? data.toolName}
          </p>
        </div>
      </div>

      {/* Status strip */}
      <div className="flex items-center gap-2 text-[11px]">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium",
            {
              success: "border-emerald-400/30 bg-emerald-400/10 text-emerald-400",
              error: "border-red-400/30 bg-red-400/10 text-red-400",
              pending: "border-primary/30 bg-primary/10 text-primary",
              approval: "border-orange-400/30 bg-orange-400/10 text-orange-400",
              planned: "border-border/40 bg-muted/20 text-muted-foreground",
            }[data.status]
          )}
        >
          {data.status === "success" && <CheckCircle2 className="h-3 w-3" />}
          {data.status === "error" && <XCircle className="h-3 w-3" />}
          {data.status === "planned" && <GitBranch className="h-3 w-3" />}
          {data.status === "approval" && <ShieldAlert className="h-3 w-3" />}
          {data.status}
        </span>
        {data.durationMs > 0 && (
          <span className="text-muted-foreground/50 flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {fmtMs(data.durationMs)}
          </span>
        )}
      </div>

      {/* Error */}
      {data.errorMsg && (
        <div className="rounded-lg border border-red-400/30 bg-red-400/5 p-2.5">
          <p className="text-[11px] font-medium text-red-400 mb-1">Error</p>
          <p className="text-[10px] font-mono text-red-400/80 whitespace-pre-wrap break-all">
            {data.errorMsg}
          </p>
        </div>
      )}

      {/* Inputs */}
      {hasArgs && (
        <div>
          <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Inputs
          </p>
          <pre className="text-[10px] font-mono text-muted-foreground/70 bg-muted/20 rounded-lg border border-border/30 p-2.5 overflow-x-auto whitespace-pre-wrap break-all">
            {JSON.stringify(data.args, null, 2)}
          </pre>
        </div>
      )}

      {/* Output */}
      {hasOutput && (
        <div>
          <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Output
          </p>
          {data.output.answer != null && (
            <p className="text-xs text-foreground/80 mb-2 leading-relaxed">
              {String(data.output.answer as string)}
            </p>
          )}
          <pre className="text-[10px] font-mono text-muted-foreground/70 bg-muted/20 rounded-lg border border-border/30 p-2.5 overflow-x-auto whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
            {JSON.stringify(data.output, null, 2)}
          </pre>
        </div>
      )}

      {!hasArgs && !hasOutput && !data.errorMsg && (
        <p className="text-xs text-muted-foreground/40 italic">No details available.</p>
      )}
    </div>
  );
}

// ── Main overlay component ────────────────────────────────────────────────────

interface AgentFlowVizProps {
  steps: ToolResult[];
  plannedSteps?: PlannedToolCall[];
  onClose: () => void;
}

type ViewMode = "executed" | "plan";

export function AgentFlowViz({ steps, plannedSteps, onClose }: AgentFlowVizProps) {
  const hasPlan = (plannedSteps?.length ?? 0) > 0;
  const hasExecuted = steps.length > 0;

  const [viewMode, setViewMode] = useState<ViewMode>(hasExecuted ? "executed" : "plan");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { nodes: initNodes, edges: initEdges } = useMemo(() => {
    if (viewMode === "plan" && hasPlan) return buildFromPlan(plannedSteps!);
    return buildFromExecuted(steps);
  }, [viewMode, steps, plannedSteps, hasPlan]);

  const [nodes, , onNodesChange] = useNodesState<StepNode>(initNodes);
  const [edges, , onEdgesChange] = useEdgesState(initEdges);

  const selectedNode = nodes.find((n) => n.id === selectedId);
  const selectedData = selectedNode?.data ?? null;

  const handleNodeClick = useCallback((_evt: React.MouseEvent, node: StepNode) => {
    setSelectedId((prev) => (prev === node.id ? null : node.id));
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-stretch bg-background/95 backdrop-blur-md">
      {/* Header */}
      <div className="absolute top-0 left-0 right-0 z-10 flex h-12 items-center justify-between px-4 border-b border-border/60 bg-background/80 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-gradient-primary elevation-glow-sm">
            <GitBranch className="h-3.5 w-3.5 text-white" />
          </div>
          <span className="text-sm font-semibold text-foreground">Agent Workflow</span>

          {/* View toggle */}
          <div className="flex items-center gap-1 ml-4 bg-muted/30 rounded-lg p-0.5">
            <button
              onClick={() => { setViewMode("executed"); setSelectedId(null); }}
              disabled={!hasExecuted}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-colors disabled:opacity-30 disabled:cursor-not-allowed",
                viewMode === "executed"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Executed
              {hasExecuted && (
                <span className="ml-1.5 text-[10px] bg-primary/15 text-primary rounded-full px-1.5 py-0.5">
                  {steps.length}
                </span>
              )}
            </button>
            <button
              onClick={() => { setViewMode("plan"); setSelectedId(null); }}
              disabled={!hasPlan}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-colors disabled:opacity-30 disabled:cursor-not-allowed",
                viewMode === "plan"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Plan
              {hasPlan && (
                <span className="ml-1.5 text-[10px] bg-muted/50 text-muted-foreground rounded-full px-1.5 py-0.5">
                  {plannedSteps!.length}
                </span>
              )}
            </button>
          </div>
        </div>

        {/* Stats */}
        {hasExecuted && viewMode === "executed" && (
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground/60 mr-4">
            <span className="flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3 text-emerald-400" />
              {steps.filter((s) => !s.error).length} ok
            </span>
            {steps.filter((s) => s.error).length > 0 && (
              <span className="flex items-center gap-1">
                <XCircle className="h-3 w-3 text-red-400" />
                {steps.filter((s) => s.error).length} failed
              </span>
            )}
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {fmtMs(steps.reduce((a, s) => a + s.duration_ms, 0))} total
            </span>
          </div>
        )}

        <button
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/20 transition-colors"
          aria-label="Close"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Body */}
      <div className="flex w-full pt-12">
        {/* Flow canvas */}
        <div className="flex-1 min-w-0">
          {initNodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-4">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-muted/20">
                <GitBranch className="h-7 w-7 text-muted-foreground/20" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-muted-foreground">No steps to display</p>
                <p className="text-xs text-muted-foreground/50 mt-1">
                  Run a goal or use Explain to see the workflow graph
                </p>
              </div>
            </div>
          ) : (
            <ReactFlow
              key={`${viewMode}-${initNodes.length}`}
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={handleNodeClick}
              fitView
              fitViewOptions={{ padding: 0.3, maxZoom: 1.2 }}
              colorMode="dark"
              nodesDraggable
              nodesConnectable={false}
              elementsSelectable
              proOptions={{ hideAttribution: true }}
            >
              <Background
                variant={BackgroundVariant.Dots}
                gap={24}
                size={1}
                color="hsl(var(--border) / 0.4)"
              />
              <Controls
                showInteractive={false}
                className="[&>button]:bg-card/80 [&>button]:border-border/40 [&>button]:text-muted-foreground"
              />
            </ReactFlow>
          )}
        </div>

        {/* Detail panel */}
        <div className="w-80 shrink-0 border-l border-border/60 bg-card/40 flex flex-col">
          <div className="px-4 py-2.5 border-b border-border/40 shrink-0">
            <p className="text-xs font-semibold text-muted-foreground">
              {selectedData ? "Step details" : "Select a node"}
            </p>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto">
            <DetailPanel data={selectedData} />
          </div>
        </div>
      </div>
    </div>
  );
}
