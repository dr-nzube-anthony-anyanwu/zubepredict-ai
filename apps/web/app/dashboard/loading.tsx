export default function Loading() {
  return <main className="dashboard-main"><div className="skeleton hero-skeleton" /><div className="metric-grid">{[1,2,3,4].map((item) => <div className="skeleton metric" key={item} />)}</div></main>;
}
