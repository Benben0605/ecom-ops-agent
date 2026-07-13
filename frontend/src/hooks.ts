import { useCallback, useEffect, useRef, useState } from "react";

import {
  type DashboardSelection,
  fetchEvalDashboard,
  fetchL2FixturesDashboard,
  fetchL2Dashboard,
  type EvalDashboardData,
  type L2DashboardData,
  type L2FixturesDashboardData,
} from "./api";

interface QueryState<T> {
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

function useQuery<T>(fetcher: () => Promise<T>, enabled = true): QueryState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const load = useCallback(async () => {
    if (!enabled) return;
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
  }, [enabled, fetcher]);

  useEffect(() => {
    mounted.current = true;
    if (enabled) {
      void load();
    } else {
      setData(null);
      setError(null);
      setLoading(false);
      setRefreshing(false);
    }
    return () => {
      mounted.current = false;
    };
  }, [enabled, load]);

  return { data, loading, refreshing, error, refetch: load };
}

export function useEval(selection: DashboardSelection, enabled = true): QueryState<EvalDashboardData> {
  const fetcher = useCallback(
    () => fetchEvalDashboard(selection),
    [selection.source, selection.expId, selection.variant],
  );
  return useQuery(fetcher, enabled);
}

export function useL2(selection: DashboardSelection, enabled = true): QueryState<L2DashboardData> {
  const fetcher = useCallback(
    () => fetchL2Dashboard(selection),
    [selection.source, selection.expId, selection.variant],
  );
  return useQuery(fetcher, enabled);
}

export function useL2Fixtures(
  selection: DashboardSelection,
  enabled = true,
): QueryState<L2FixturesDashboardData> {
  const fetcher = useCallback(
    () => fetchL2FixturesDashboard(selection),
    [selection.source, selection.expId, selection.variant],
  );
  return useQuery(fetcher, enabled && Boolean(selection.expId && selection.variant));
}
