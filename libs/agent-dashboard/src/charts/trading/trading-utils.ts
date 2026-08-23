import type { Time } from 'lightweight-charts';

export function toUnixSeconds(value: unknown): Time {
  if (typeof value === 'number') return value as Time;
  return Math.floor(new Date(String(value)).getTime() / 1000) as Time;
}

export function num(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isNaN(n) ? 0 : n;
}
