import { Navigate, Route, Routes, useLocation } from "react-router-dom";

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
  const evalQuery = useEval();
  const l2Query = useL2();
  const isOverview = location.pathname === "/";
  const isL1 = location.pathname === "/l1";
  const isL2 = location.pathname === "/l2";
  const generatedAt = isL1 ? evalQuery.data?.generated_at : isL2 ? l2Query.data?.generated_at : isOverview ? (evalQuery.data?.generated_at ?? l2Query.data?.generated_at) : null;
  const refreshing = isL1 ? evalQuery.refreshing : isL2 ? l2Query.refreshing : isOverview ? evalQuery.refreshing || l2Query.refreshing : false;
  const refresh = isL1 ? evalQuery.refetch : isL2 ? l2Query.refetch : isOverview ? () => Promise.all([evalQuery.refetch(), l2Query.refetch()]).then(() => undefined) : undefined;

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="workspace">
        <TopBar title={titles[location.pathname] ?? "Agent 评估工作台"} generatedAt={generatedAt} refreshing={refreshing} onRefresh={refresh} />
        <main className="content">
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
