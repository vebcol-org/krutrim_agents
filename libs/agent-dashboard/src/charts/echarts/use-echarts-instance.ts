import { useEffect, useRef, type RefObject } from 'react';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';

/**
 * Owns one ECharts instance's full lifecycle against a container ref: init
 * (bound to `themeName` — ECharts themes are set at init time, so a theme
 * change re-creates the instance), auto-resize via ResizeObserver, and
 * dispose on unmount. `option` updates call `setOption` with `notMerge:
 * true` so switching series shape (e.g. fewer categories after a filter)
 * doesn't leave stale series behind.
 */
export function useEChartsInstance(containerRef: RefObject<HTMLDivElement | null>, option: EChartsOption, themeName: string) {
  const instanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const instance = echarts.init(container, themeName);
    instanceRef.current = instance;

    const resizeObserver = new ResizeObserver(() => instance.resize());
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      instance.dispose();
      instanceRef.current = null;
    };
  }, [themeName]);

  useEffect(() => {
    instanceRef.current?.setOption(option, true);
  }, [option]);

  return instanceRef;
}
