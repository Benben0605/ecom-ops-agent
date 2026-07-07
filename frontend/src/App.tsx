import { useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes, useLocation, useSearchParams } from "react-router-dom";

import type { DashboardSelection, ExperimentManifest } from "./api";
import { fetchExperiments } from "./api";
import DataSourceControls from "./components/DataSourceControls";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import { useEval, useL2 } from "./hooks";
import ABCompare from "./views/ABCompare";
import Overview from "./views/Overview";
import Playground from "./views/Playground";
import QualityL2 from "./views/QualityL2";
import RoutingL1 from "./views/RoutingL1";

const titles: Record<string, string> = {
  "/": "总览",
  "/l1": "L1 路由评估",
  "/l2": "L2 回复质量",
  "/ab": "A/B 对比",
  "/playground": "Playground",
};

export default function App() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [experiments, setExperiments] = useState<ExperimentManifest[]>([]);
  const [experimentsLoading, setExperimentsLoading] = useState(true);
  const isOverview = location.pathname === "/";
  const isL1 = location.pathname === "/l1";
  const isL2 = location.pathname === "/l2";
  const source = searchParams.get("source") === "experiment" || searchParams.has("exp")
    ? "experiment"
    : "legacy";
  const requestedExpId = searchParams.get("exp") ?? undefined;
  const requestedVariant = searchParams.get("variant") ?? undefined;
  const agentExperiments = useMemo(
    () => experiments.filter((experiment) => experiment.track === "agent"),
    [experiments],
  );
  const selectedManifest = agentExperiments.find((experiment) => experiment.exp_id === requestedExpId)
    ?? agentExperiments[0]
    ?? null;
  const selectedVariant = selectedManifest?.variants.find((variant) => variant.name === requestedVariant)
    ?? selectedManifest?.variants[0]
    ?? null;
  const selection: DashboardSelection = source === "experiment" && selectedManifest && selectedVariant
    ? { source: "experiment", expId: selectedManifest.exp_id, variant: selectedVariant.name }
    : { source: "legacy" };

  const evalQuery = useEval(selection);
  const l2Query = useL2(selection);
  const showSourceControls = isOverview || isL1 || isL2;
  const generatedAt = isL1 ? evalQuery.data?.generated_at : isL2 ? l2Query.data?.generated_at : isOverview ? (evalQuery.data?.generated_at ?? l2Query.data?.generated_at) : null;
  const refreshing = isL1 ? evalQuery.refreshing : isL2 ? l2Query.refreshing : isOverview ? evalQuery.refreshing || l2Query.refreshing : false;
  const refresh = isL1 ? evalQuery.refetch : isL2 ? l2Query.refetch : isOverview ? () => Promise.all([evalQuery.refetch(), l2Query.refetch()]).then(() => undefined) : undefined;

  useEffect(() => {
    fetchExperiments()
      .then(setExperiments)
      .finally(() => setExperimentsLoading(false));
  }, []);

  useEffect(() => {
    if (source !== "experiment" || !selectedManifest || !selectedVariant) return;
    if (
      requestedExpId === selectedManifest.exp_id
      && requestedVariant === selectedVariant.name
      && searchParams.get("source") === "experiment"
    ) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.set("source", "experiment");
    next.set("exp", selectedManifest.exp_id);
    next.set("variant", selectedVariant.name);
    setSearchParams(next, { replace: true });
  }, [
    requestedExpId,
    requestedVariant,
    searchParams,
    selectedManifest,
    selectedVariant,
    setSearchParams,
    source,
  ]);

  const setLegacy = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("source");
    next.delete("exp");
    next.delete("variant");
    setSearchParams(next);
  };

  const setExperiment = (expId: string) => {
    const manifest = agentExperiments.find((experiment) => experiment.exp_id === expId);
    const next = new URLSearchParams(searchParams);
    next.set("source", "experiment");
    next.set("exp", expId);
    next.set("variant", manifest?.variants[0]?.name ?? "");
    setSearchParams(next);
  };

  const setVariant = (variant: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("source", "experiment");
    if (selection.expId) next.set("exp", selection.expId);
    next.set("variant", variant);
    setSearchParams(next);
  };

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="workspace">
        <TopBar title={titles[location.pathname] ?? "Agent 评估工作台"} generatedAt={generatedAt} refreshing={refreshing} onRefresh={refresh} />
        <main className="content">
          {showSourceControls && (
            <DataSourceControls
              experiments={experiments}
              loading={experimentsLoading}
              selection={selection}
              onLegacy={setLegacy}
              onExperiment={setExperiment}
              onVariant={setVariant}
            />
          )}
          <Routes>
            <Route path="/" element={<Overview evalQuery={evalQuery} l2Query={l2Query} />} />
            <Route path="/l1" element={<RoutingL1 query={evalQuery} />} />
            <Route path="/l2" element={<QualityL2 query={l2Query} />} />
            <Route path="/ab" element={<ABCompare />} />
            <Route path="/playground" element={<Playground />} />
            <Route path="/dashboard" element={<Navigate to="/l1" replace />} />
            <Route path="/l2-dashboard" element={<Navigate to="/l2" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
