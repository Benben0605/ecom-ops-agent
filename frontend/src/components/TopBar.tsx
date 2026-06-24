interface TopBarProps {
  title: string;
  generatedAt?: string | null;
  refreshing?: boolean;
  onRefresh?: () => void;
}

function formatTime(value?: string | null) {
  if (!value) return "等待数据";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export default function TopBar({ title, generatedAt, refreshing, onRefresh }: TopBarProps) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Evaluation workspace</p>
        <h1>{title}</h1>
      </div>
      {onRefresh && (
        <div className="topbar-actions">
          <span className="generated-at">数据于 <b>{formatTime(generatedAt)}</b> 生成</span>
          <button
            className="icon-button"
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            title="刷新数据"
            aria-label="刷新数据"
          >
            <svg className={refreshing ? "spin" : ""} viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6" /></svg>
          </button>
        </div>
      )}
    </header>
  );
}
