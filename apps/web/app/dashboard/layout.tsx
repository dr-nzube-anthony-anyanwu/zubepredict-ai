import Link from "next/link";
import { authenticatedUser } from "../../lib/api";
import { signOut } from "./actions";
import DashboardNav from "./dashboard-nav";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const user = await authenticatedUser();
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/dashboard"><span className="brand-mark">ZP</span><span>ZubePredict AI</span></Link>
        <p className="sidebar-tagline">From raw data to defensible decisions.</p>
        <DashboardNav />
        <div className="sidebar-foot">
          <div className="user-chip"><span>{(user.email || "U").slice(0, 1).toUpperCase()}</span><div><strong>{user.email}</strong><small>Authenticated workspace</small></div></div>
          <form action={signOut}><button className="text-button">Sign out</button></form>
        </div>
      </aside>
      <div className="workspace">{children}</div>
    </div>
  );
}
