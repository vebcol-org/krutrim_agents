import type { PointerEvent as ReactPointerEvent } from 'react';

export interface ResizeHandleProps {
  onResize: (deltaX: number) => void;
  onReset: () => void;
}

/** Drag the left edge of the output panel to resize it; double-click resets to the default width. */
export function ResizeHandle({ onResize, onReset }: ResizeHandleProps) {
  function handlePointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    e.preventDefault();
    const handle = e.currentTarget;
    handle.setPointerCapture(e.pointerId);
    let lastX = e.clientX;

    function handlePointerMove(ev: PointerEvent) {
      onResize(ev.clientX - lastX);
      lastX = ev.clientX;
    }
    function handlePointerUp(ev: PointerEvent) {
      handle.releasePointerCapture(ev.pointerId);
      handle.removeEventListener('pointermove', handlePointerMove);
      handle.removeEventListener('pointerup', handlePointerUp);
    }

    handle.addEventListener('pointermove', handlePointerMove);
    handle.addEventListener('pointerup', handlePointerUp);
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize output panel"
      onPointerDown={handlePointerDown}
      onDoubleClick={onReset}
      className="group relative w-1.5 shrink-0 cursor-col-resize touch-none"
    >
      <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border transition-colors group-hover:bg-primary group-active:bg-primary" />
    </div>
  );
}
