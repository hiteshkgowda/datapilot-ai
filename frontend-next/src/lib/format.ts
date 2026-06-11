/**
 * Display formatting utilities — pure functions, no side effects.
 */

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, i);
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[i]}`;
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

export function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function formatDtype(dtype: string): string {
  if (dtype.startsWith("int") || dtype.startsWith("uint")) return "integer";
  if (dtype.startsWith("float")) return "float";
  if (dtype === "bool") return "boolean";
  if (dtype.startsWith("datetime")) return "datetime";
  if (dtype === "object" || dtype.startsWith("string")) return "string";
  return dtype;
}

/** Returns true for pandas dtypes that represent numbers */
export function isNumericDtype(dtype: string): boolean {
  return (
    dtype.startsWith("int") ||
    dtype.startsWith("uint") ||
    dtype.startsWith("float")
  );
}
