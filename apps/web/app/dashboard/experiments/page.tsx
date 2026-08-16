import type { Metadata } from "next";
import DashboardRoute from "../dashboard-page";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Experiments", description: "Define, approve and run durable machine-learning experiments with visible guardrails." };

export default function ExperimentsPage() {
  return <DashboardRoute view="experiments" />;
}
