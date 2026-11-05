/** Rows still meant to be monitored. Removal intent is not an active monitor. */
export function countIntendedMonitors(rows: readonly { desired_state: string }[]): number {
  let count = 0;
  for (const row of rows) if (row.desired_state !== "removed") count += 1;
  return count;
}

/**
 * Default management list. Hide a removal once the operation succeeded, even when
 * observed_state is no longer "absent" (the API reports unknown after the observation window).
 * A removal that has not succeeded stays visible.
 */
export function isVisibleMonitor(row: { desired_state: string; operation_state: string }): boolean {
  return !(row.desired_state === "removed" && row.operation_state === "succeeded");
}

export function visibleMonitors<T extends { desired_state: string; operation_state: string }>(rows: readonly T[]): T[] {
  return rows.filter(isVisibleMonitor);
}
