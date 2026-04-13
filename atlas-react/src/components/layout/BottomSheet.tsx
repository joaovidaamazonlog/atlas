import React, { useRef, useState, useEffect, useCallback } from 'react';

interface BottomSheetProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  snapPoints?: number[];
}

export const BottomSheet: React.FC<BottomSheetProps> = ({
  isOpen,
  onClose,
  children,
  snapPoints,
}) => {
  const defaultSnapPoints =
    typeof window !== 'undefined'
      ? [200, 400, Math.round(window.innerHeight * 0.85)]
      : [200, 400, 600];

  const points = snapPoints ?? defaultSnapPoints;
  const [currentSnap, setCurrentSnap] = useState(points[0]);
  const [dragging, setDragging] = useState(false);
  const dragStartY = useRef(0);
  const dragStartSnap = useRef(0);

  // Reset snap when opened
  useEffect(() => {
    if (isOpen) setCurrentSnap(points[0]);
  }, [isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  const snapToNearest = useCallback(
    (height: number) => {
      const nearest = points.reduce((prev, curr) =>
        Math.abs(curr - height) < Math.abs(prev - height) ? curr : prev
      );
      setCurrentSnap(nearest);
    },
    [points]
  );

  const handlePointerDown = (e: React.PointerEvent) => {
    setDragging(true);
    dragStartY.current = e.clientY;
    dragStartSnap.current = currentSnap;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!dragging) return;
    const delta = dragStartY.current - e.clientY;
    const newHeight = Math.max(points[0], Math.min(points[points.length - 1], dragStartSnap.current + delta));
    setCurrentSnap(newHeight);
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (!dragging) return;
    setDragging(false);
    const delta = dragStartY.current - e.clientY;
    const newHeight = dragStartSnap.current + delta;

    // If dragged far down below minimum, close
    if (newHeight < points[0] - 80) {
      onClose();
      return;
    }
    snapToNearest(newHeight);
  };

  const translateY = isOpen ? 0 : '100%';

  return (
    <>
      {/* Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 transition-opacity duration-300"
          style={{ zIndex: 'var(--z-overlay)' as unknown as number }}
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sheet */}
      <div
        role="dialog"
        aria-modal="true"
        className="fixed bottom-0 left-0 right-0 rounded-t-2xl flex flex-col overflow-hidden"
        style={{
          height: `${currentSnap}px`,
          zIndex: 'var(--z-drawer)' as unknown as number,
          backgroundColor: 'var(--color-navy)',
          borderTop: '1px solid var(--border-color)',
          transform: `translateY(${translateY})`,
          transition: dragging ? 'none' : 'transform 300ms ease, height 300ms ease',
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        {/* Handle bar */}
        <div
          className="flex justify-center items-center py-3 cursor-grab active:cursor-grabbing shrink-0"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
        >
          <div
            className="w-10 h-1 rounded-full"
            style={{ backgroundColor: 'var(--border-color-strong)' }}
          />
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </>
  );
};
