import { useEffect } from "react";

interface CaseDrawerProps {
  open: boolean;
  title: string;
  subtitle?: React.ReactNode;
  width?: "normal" | "wide";
  onClose: () => void;
  children: React.ReactNode;
}

export default function CaseDrawer({ open, title, subtitle, width = "normal", onClose, children }: CaseDrawerProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    document.body.classList.add("drawer-open");
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.classList.remove("drawer-open");
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="drawer-layer" role="presentation">
      <button className="drawer-backdrop" type="button" onClick={onClose} aria-label="关闭详情" />
      <aside className={`drawer drawer-${width}`} role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <header className="drawer-header">
          <div>
            <h2 id="drawer-title">{title}</h2>
            {subtitle && <div className="drawer-subtitle">{subtitle}</div>}
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭详情">
            <svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18" /></svg>
          </button>
        </header>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}
