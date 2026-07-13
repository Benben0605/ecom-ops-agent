import type { DashboardSelection, ExperimentManifest } from "../api";

interface DataSourceControlsProps {
  experiments: ExperimentManifest[];
  loading: boolean;
  selection: DashboardSelection;
  onLegacy: () => void;
  onExperiment: (expId: string) => void;
  onVariant: (variant: string) => void;
  allowLegacy?: boolean;
  emptyLabel?: string;
}

export default function DataSourceControls({
  experiments,
  loading,
  selection,
  onLegacy,
  onExperiment,
  onVariant,
  allowLegacy = true,
  emptyLabel = "无实验",
}: DataSourceControlsProps) {
  const selected = experiments.find((experiment) => experiment.exp_id === selection.expId) ?? null;
  const variants = selected?.variants ?? [];
  const canUseExperiment = experiments.length > 0;

  return (
    <section className="panel data-source-panel">
      <div className="source-segmented">
        {allowLegacy && (
          <button
            type="button"
            className={selection.source === "legacy" ? "active" : ""}
            onClick={onLegacy}
          >
            最新日志
          </button>
        )}
        <button
          type="button"
          className={selection.source === "experiment" ? "active" : ""}
          disabled={!canUseExperiment}
          onClick={() => {
            const first = experiments[0];
            if (first) onExperiment(first.exp_id);
          }}
        >
          实验
        </button>
      </div>
      <div className="source-fields">
        <label>
          <span>experiment</span>
          <select
            value={selection.expId ?? ""}
            disabled={selection.source !== "experiment" || loading || !canUseExperiment}
            onChange={(event) => onExperiment(event.target.value)}
          >
            {!canUseExperiment && <option value="">{emptyLabel}</option>}
            {experiments.map((experiment) => (
              <option key={experiment.exp_id} value={experiment.exp_id}>
                {experiment.exp_id}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>variant</span>
          <select
            value={selection.variant ?? ""}
            disabled={selection.source !== "experiment" || !selected}
            onChange={(event) => onVariant(event.target.value)}
          >
            {!selected && <option value="">选择实验</option>}
            {variants.map((variant) => (
              <option key={variant.name} value={variant.name}>
                {variant.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="source-meta">
        {selection.source === "legacy" ? (
          <span>logs/*.json</span>
        ) : selected ? (
          <>
            <span>{selected.name}</span>
            <span>n={selected.provenance.n}</span>
            <span>{selected.provenance.timestamp}</span>
          </>
        ) : (
          <span>{loading ? "加载实验列表..." : "未选择实验"}</span>
        )}
      </div>
    </section>
  );
}
