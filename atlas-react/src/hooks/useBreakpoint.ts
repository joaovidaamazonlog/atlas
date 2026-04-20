import { useState, useEffect } from 'react';

export type Breakpoint = 'mobile' | 'tablet' | 'laptop' | 'notebook' | 'desktop';

const QUERIES: Record<Breakpoint, string> = {
  mobile:   '(max-width: 767px)',
  tablet:   '(min-width: 768px) and (max-width: 1023px)',
  laptop:   '(min-width: 1024px) and (max-width: 1365px)',
  notebook: '(min-width: 1366px) and (max-width: 1439px)',
  desktop:  '(min-width: 1440px)',
};

function getInitialBreakpoint(): Breakpoint {
  if (typeof window === 'undefined') return 'desktop';

  for (const [bp, query] of Object.entries(QUERIES) as [Breakpoint, string][]) {
    if (window.matchMedia(query).matches) return bp;
  }

  return 'desktop';
}

export function useBreakpoint(): Breakpoint {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(getInitialBreakpoint);

  useEffect(() => {
    const mediaQueryLists = Object.entries(QUERIES).map(([bp, query]) => {
      const mql = window.matchMedia(query);
      const handler = (e: MediaQueryListEvent) => {
        if (e.matches) setBreakpoint(bp as Breakpoint);
      };
      mql.addEventListener('change', handler);
      return { mql, handler };
    });

    return () => {
      mediaQueryLists.forEach(({ mql, handler }) => {
        mql.removeEventListener('change', handler);
      });
    };
  }, []);

  return breakpoint;
}
