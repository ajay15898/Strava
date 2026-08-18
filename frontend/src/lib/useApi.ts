import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../api/client";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  status: number | null;
  loading: boolean;
  reload: () => void;
}

/** Minimal fetch-on-mount hook.
 *  Deliberately not a cache library — this dashboard reads a handful of
 *  endpoints once. Reach for TanStack Query when mutations arrive in M4. */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    run()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setStatus(200);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setData(null);
        setStatus(err instanceof ApiError ? err.status : null);
        setError(err instanceof Error ? err.message : "Something went wrong");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [run, nonce]);

  return { data, error, status, loading, reload: () => setNonce((n) => n + 1) };
}
