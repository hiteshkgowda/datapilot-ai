"use client";

import { motion, useReducedMotion, type Variants } from "framer-motion";
import { DatasetCard } from "./DatasetCard";
import type { DatasetMetadata } from "@/lib/api/types";

const containerVariants: Variants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.07,
    },
  },
};

interface DatasetGridProps {
  datasets: DatasetMetadata[];
}

export function DatasetGrid({ datasets }: DatasetGridProps) {
  const shouldReduceMotion = useReducedMotion();

  return (
    <motion.div
      variants={shouldReduceMotion ? {} : containerVariants}
      initial="hidden"
      animate="show"
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3"
    >
      {datasets.map((ds) => (
        <DatasetCard key={ds.id} dataset={ds} />
      ))}
    </motion.div>
  );
}
