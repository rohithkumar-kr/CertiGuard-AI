import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export interface RouteMatch {
  /** Full path (without leading `#`), e.g. `/investigations/V2026-8F3C9A1B`. */
  path: string;
  params: Record<string, string>;
}

interface RouterContextValue {
  path: string;
  route: RouteMatch;
  navigate: (to: string) => void;
}

const RouterContext = createContext<RouterContextValue | null>(null);

function parseHash(): string {
  const raw = window.location.hash.replace(/^#/, "");
  const clean = raw.startsWith("/") ? raw : `/${raw}`;
  const normalized = clean.replace(/\/+$/, "");
  return normalized === "" ? "/" : normalized;
}

export function navigate(to: string): void {
  const target = to.startsWith("/") ? to : `/${to}`;
  if (parseHash() === target) {
    window.scrollTo({ top: 0, behavior: "smooth" });
    return;
  }
  window.location.hash = target;
}

export function useRouter(): RouterContextValue {
  const ctx = useContext(RouterContext);
  if (!ctx) {
    throw new Error("useRouter must be used within a <Router>.");
  }
  return ctx;
}

function matchRoute(pattern: string, path: string): RouteMatch | null {
  const pParts = pattern.split("/").filter(Boolean);
  const parts = path.split("/").filter(Boolean);
  if (pParts.length !== parts.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < pParts.length; i += 1) {
    if (pParts[i].startsWith(":")) {
      try {
        params[pParts[i].slice(1)] = decodeURIComponent(parts[i]);
      } catch {
        params[pParts[i].slice(1)] = parts[i];
      }
    } else if (pParts[i] !== parts[i]) {
      return null;
    }
  }
  return { path, params };
}

export interface Route {
  path: string;
  element: ReactNode;
}

interface RouterProps {
  routes: Route[];
  fallback?: ReactNode;
}

export function Router({ routes, fallback }: RouterProps) {
  const [path, setPath] = useState<string>(() => parseHash());

  useEffect(() => {
    const onHashChange = () => {
      setPath(parseHash());
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigateFn = useCallback((to: string) => navigate(to), []);

  let matched: { match: RouteMatch; element: ReactNode } | null = null;
  for (const r of routes) {
    const m = matchRoute(r.path, path);
    if (m) {
      matched = { match: m, element: r.element };
      break;
    }
  }

  const value: RouterContextValue = {
    path,
    route: matched ? matched.match : { path, params: {} },
    navigate: navigateFn,
  };

  return (
    <RouterContext.Provider value={value}>
      {matched ? matched.element : fallback}
    </RouterContext.Provider>
  );
}

export function Link({
  to,
  className,
  children,
  onClick,
  "aria-label": ariaLabel,
}: {
  to: string;
  className?: string;
  children: ReactNode;
  onClick?: () => void;
  "aria-label"?: string;
}) {
  const { navigate } = useRouter();
  return (
    <a
      href={`#${to}`}
      className={className}
      aria-label={ariaLabel}
      onClick={(e) => {
        e.preventDefault();
        onClick?.();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}