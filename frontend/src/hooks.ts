import { useCallback, useEffect, useRef, useState } from "react";

import {
  type DashboardSelection,
  fetchEvalDashboard,
  fetchL2Dashboard,
  type EvalDashboardData,
  type L2DashboardData,
} from "./api";

interface QueryState<T> {
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

function useQuery<T>(fetcher: () => Promise<T>): QueryState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const load = useCallback(async () => {
    setError(null);
    setRefreshing(true);
    try {
      const next = await fetcher();
      if (mounted.current) setData(next);
    } catch (cause) {
      if (mounted.current) {
        setError(cause instanceof Error ? cause.message : "接口拉取失败");
      }
    } finally {
      if (mounted.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [fetcher]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
    };
  }, [load]);

  return { data, loading, refreshing, error, refetch: load };
}

export function useEval(selection: DashboardSelection): QueryState<EvalDashboardData> {
  const fetcher = useCallback(
    () => fetchEvalDashboard(selection),
    [selection.source, selection.expId, selection.variant],
  );
  return useQuery(fetcher);
}

export function useL2(selection: DashboardSelection): QueryState<L2DashboardData> {
  const fetcher = useCallback(
    () => fetchL2Dashboard(selection),
    [selection.source, selection.expId, selection.variant],
  );
  return useQuery(fetcher);
}
