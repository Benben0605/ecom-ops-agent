import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/", label: "总览", icon: "overview", end: true },
  { to: "/l1", label: "L1 路由评估", icon: "route" },
  { to: "/l2", label: "L2 回复质量", icon: "quality" },
  { to: "/judge", label: "Judge 夹具", icon: "judge" },
  { to: "/ab", label: "A/B 对比", icon: "ab" },
  { to: "/playground", label: "Playground", icon: "chat" },
] as const;

function NavIcon({ name }: { name: string }) {
  if (name === "route") {
    return <svg viewBox="0 0 24 24"><path d="M6 4v4a4 4 0 0 0 4 4h8M14 8l4 4-4 4M6 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM6 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" /></svg>;
  }
  if (name === "quality") {
    return <svg viewBox="0 0 24 24"><path d="m12 3 7 3v5c0 4.6-2.8 8.1-7 10-4.2-1.9-7-5.4-7-10V6l7-3Z" /><path d="m9 12 2 2 4-5" /></svg>;
  }
  if (name === "judge") {
    return <svg viewBox="0 0 24 24"><path d="M12 3 4 7v5c0 4.4 3.1 7.6 8 9 4.9-1.4 8-4.6 8-9V7l-8-4Z" /><path d="M8 12h8M10 9v6M14 9v6" /></svg>;
  }
  if (name === "ab") {
    return <svg viewBox="0 0 24 24"><path d="M4 6h6M4 12h6M4 18h6M14 6h6M14 12h6M14 18h6M12 3v18" /></svg>;
  }
  if (name === "chat") {
    return <svg viewBox="0 0 24 24"><path d="M5 18 3 21v-5a8 8 0 1 1 4 3.5" /></svg>;
  }
  return <svg viewBox="0 0 24 24"><path d="M4 13h6V4H4v9Zm10 7h6v-9h-6v9ZM4 20h6v-3H4v3Zm10-13h6V4h-6v3Z" /></svg>;
}

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">◆</span>
        <div>
          <strong>ecom·eval</strong>
          <span>Agent 评估工作台</span>
        </div>
      </div>
      <nav className="nav-list" aria-label="主导航">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
          >
            <NavIcon name={item.icon} />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        <a href="https://github.com/Benben0605/ecom-ops-agent#评估体系" target="_blank" rel="noreferrer">
          方法论 <span aria-hidden="true">↗</span>
        </a>
        <span>evaluation system · v2.0</span>
      </div>
    </aside>
  );
}
