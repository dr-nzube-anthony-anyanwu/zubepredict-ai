import type { Metadata } from "next";
import DashboardRoute from "../dashboard-page";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Evidence", description: "Review verified results, limitations and private report artifacts." };

export default function EvidencePage() {
  return <DashboardRoute view="evidence" />;
}
