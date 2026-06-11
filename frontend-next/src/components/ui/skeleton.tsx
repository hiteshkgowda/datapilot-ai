import { cn } from "@/lib/utils";

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Pulse with the shimmer animation (default true) */
  animate?: boolean;
}

export function Skeleton({ className, animate = true, ...props }: SkeletonProps) {
  return (
    <div
      className={cn(
        "rounded-md bg-muted",
        animate && "skeleton",
        className
      )}
      aria-hidden="true"
      {...props}
    />
  );
}
