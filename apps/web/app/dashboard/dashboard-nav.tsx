"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  ["/dashboard", "Overview", "⌂"],
  ["/dashboard/projects", "Projects", "◇"],
  ["/dashboard/experiments", "Experiments", "◫"],
  ["/dashboard/evidence", "Evidence", "✓"],
  ["/dashboard/connections", "Connections", "↗"],
] as const;

export default function DashboardNav() {
  const pathname = usePathname();
  return (
    <nav className="side-nav" aria-label="Dashboard">
      {items.map(([href, label, icon]) => {
        const active = href === "/dashboard" ? pathname === href : pathname.startsWith(href);
        return <Link href={href} className={active ? "active" : ""} aria-current={active ? "page" : undefined} key={href}><span aria-hidden="true">{icon}</span>{label}</Link>;
      })}
    </nav>
  );
}
