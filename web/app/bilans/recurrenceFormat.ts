export function formatHours(hours: number): string {
  const totalMinutes = Math.round(hours * 60);
  const wholeHours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (wholeHours === 0) return `${minutes} min`;
  if (minutes === 0) return `${wholeHours} h`;
  return `${wholeHours} h ${String(minutes).padStart(2, "0")}`;
}

export function formatCycles(cycles: number): string {
  return Math.round(cycles).toLocaleString("fr-FR");
}

export function formatSampleDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const minutes = (seconds / 60).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
  return `${minutes} min`;
}
