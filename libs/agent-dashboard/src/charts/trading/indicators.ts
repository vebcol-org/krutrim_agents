/**
 * Pure indicator math over a time-ordered `number[]` (already sorted the
 * same way rows are for candlestick charts). Each function returns entries
 * carrying the `index` they correspond to in the input array — the caller
 * (build-trading-config.ts) maps that back to a row's time — rather than a
 * same-length array padded with nulls, since `lightweight-charts`' line data
 * doesn't accept a nullable value: skipping the warm-up window entirely is
 * the standard approach.
 */

export interface IndexedValue {
  index: number;
  value: number;
}

export function computeSMA(values: number[], period: number): IndexedValue[] {
  if (period <= 0 || values.length < period) return [];
  const result: IndexedValue[] = [];
  let windowSum = 0;
  for (let i = 0; i < values.length; i++) {
    windowSum += values[i];
    if (i >= period) windowSum -= values[i - period];
    if (i >= period - 1) result.push({ index: i, value: windowSum / period });
  }
  return result;
}

export function computeEMA(values: number[], period: number): IndexedValue[] {
  if (period <= 0 || values.length < period) return [];
  const k = 2 / (period + 1);
  const result: IndexedValue[] = [];
  let ema = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  result.push({ index: period - 1, value: ema });
  for (let i = period; i < values.length; i++) {
    ema = values[i] * k + ema * (1 - k);
    result.push({ index: i, value: ema });
  }
  return result;
}

function rsiFromAverages(avgGain: number, avgLoss: number): number {
  if (avgLoss === 0) return avgGain === 0 ? 50 : 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

/** Wilder's smoothing, the standard RSI formulation. */
export function computeRSI(values: number[], period = 14): IndexedValue[] {
  if (values.length <= period) return [];

  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const delta = values[i] - values[i - 1];
    if (delta >= 0) avgGain += delta;
    else avgLoss -= delta;
  }
  avgGain /= period;
  avgLoss /= period;

  const result: IndexedValue[] = [{ index: period, value: rsiFromAverages(avgGain, avgLoss) }];

  for (let i = period + 1; i < values.length; i++) {
    const delta = values[i] - values[i - 1];
    const gain = delta > 0 ? delta : 0;
    const loss = delta < 0 ? -delta : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    result.push({ index: i, value: rsiFromAverages(avgGain, avgLoss) });
  }
  return result;
}

export interface MacdResult {
  macd: IndexedValue[];
  signal: IndexedValue[];
  histogram: IndexedValue[];
}

export function computeMACD(values: number[], fastPeriod = 12, slowPeriod = 26, signalPeriod = 9): MacdResult {
  const fastEma = computeEMA(values, fastPeriod);
  const slowEma = computeEMA(values, slowPeriod);
  if (fastEma.length === 0 || slowEma.length === 0) return { macd: [], signal: [], histogram: [] };

  const fastByIndex = new Map(fastEma.map((e) => [e.index, e.value]));
  const macd: IndexedValue[] = [];
  for (const s of slowEma) {
    const f = fastByIndex.get(s.index);
    if (f !== undefined) macd.push({ index: s.index, value: f - s.value });
  }

  // EMA the macd line's own values for the signal line, then remap its
  // (local, into-macd-array) index back to the original values-array index.
  const signalLocal = computeEMA(
    macd.map((m) => m.value),
    signalPeriod,
  );
  const signal: IndexedValue[] = signalLocal.map((s) => ({ index: macd[s.index].index, value: s.value }));

  const signalByIndex = new Map(signal.map((s) => [s.index, s.value]));
  const histogram: IndexedValue[] = [];
  for (const m of macd) {
    const sig = signalByIndex.get(m.index);
    if (sig !== undefined) histogram.push({ index: m.index, value: m.value - sig });
  }

  return { macd, signal, histogram };
}
