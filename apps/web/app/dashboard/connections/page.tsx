import type { Metadata } from "next";
import DashboardRoute from "../dashboard-page";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Connections", description: "Securely connect Telegram to the same owner-scoped ZubePredict workspace." };

export default function ConnectionsPage() {
  return <DashboardRoute view="connections" />;
}
