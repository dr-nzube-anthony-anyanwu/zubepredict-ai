import type { Metadata } from "next";
import DashboardRoute from "./dashboard-page";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Overview", description: "Your owned ZubePredict projects, experiments and evidence at a glance." };

export default function OverviewPage() {
  return <DashboardRoute view="overview" />;
}
