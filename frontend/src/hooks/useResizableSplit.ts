import { useCallback, useEffect, useRef, useState } from "react";

/** Drag-to-resize state for a two-column layout: returns the left column's
 * width in px and a mousedown handler to put on the divider between them.
 * Persists the chosen width in localStorage (keyed by `storageKey`) so it
 * survives a page reload. */
export function useResizableSplit(storageKey: string, defaultWidth: number, min = 300, max = 1400) {
  const [width, setWidth] = useState(() => {
    const saved = Number(localStorage.getItem(storageKey));
    return saved && saved >= min && saved <= max ? saved : defaultWidth;
  });
  const dragging = useRef(false);
  const containerLeft = useRef(0);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const next = Math.min(max, Math.max(min, e.clientX - containerLeft.current));
      setWidth(next);
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setWidth((w) => {
        localStorage.setItem(storageKey, String(w));
        return w;
      });
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [storageKey, min, max]);

  const onDividerMouseDown = useCallback((e: React.MouseEvent) => {
    const container = (e.currentTarget as HTMLElement).parentElement;
    containerLeft.current = container ? container.getBoundingClientRect().left : 0;
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  return { width, onDividerMouseDown };
}
