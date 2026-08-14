import Link from "next/link";
import { authenticatedUser } from "../../lib/api";
import { signOut } from "./actions";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const user = await authenticatedUser();
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/dashboard"><span className="brand-mark">ZP</span><span>ZubePredict AI</span></Link>
        <nav className="side-nav" aria-label="Dashboard">
          <a href="#overview" className="active"><span>⌂</span> Overview</a>
          <a href="#projects"><span>▦</span> Projects</a>
          <a href="#experiments"><span>◫</span> Experiments</a>
          <a href="#evidence"><span>✓</span> Evidence</a>
          <a href="#connections"><span>↗</span> Connections</a>
        </nav>
        <div className="sidebar-foot">
          <div className="user-chip"><span>{(user.email || "U").slice(0, 1).toUpperCase()}</span><div><strong>{user.email}</strong><small>Authenticated</small></div></div>
          <form action={signOut}><button className="text-button">Sign out</button></form>
        </div>
      </aside>
      <div className="workspace">{children}</div>
    </div>
  );
}
