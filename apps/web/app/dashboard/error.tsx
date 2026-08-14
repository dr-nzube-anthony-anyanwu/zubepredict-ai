"use client";

export default function DashboardError({ reset }: { reset: () => void }) {
  return <main className="dashboard-main"><section className="empty-state"><span className="empty-icon">!</span><h1>The workspace is temporarily unavailable</h1><p>Your existing experiments have not been restarted or deleted.</p><button className="button primary" onClick={reset}>Try again</button></section></main>;
}
