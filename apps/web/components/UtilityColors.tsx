"use client";
import { createContext, useCallback, useContext, type ReactNode } from "react";
import { utilityColor } from "@/lib/utils";
const Colors = createContext<Record<string, string>>({});
export const COMPARISON_COLORS = ["#2563eb", "#e87924"] as const;
export function UtilityColors({
  colors,
  children,
}: {
  colors: Record<string, string>;
  children: ReactNode;
}) {
  return <Colors.Provider value={colors}>{children}</Colors.Provider>;
}
export function useUtilityColor() {
  const colors = useContext(Colors);
  return useCallback((id: string) => colors[id] ?? utilityColor(id), [colors]);
}
