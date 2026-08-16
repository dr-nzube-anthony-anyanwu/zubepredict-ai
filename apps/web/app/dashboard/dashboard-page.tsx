import { apiFetch } from "../../lib/api";
import type { DashboardOverview, TelegramLink } from "../../lib/types";
import DashboardClient, { type DashboardView } from "./dashboard-client";

export default async function DashboardRoute({ view }: { view: DashboardView }) {
  const [overview, telegramLink] = await Promise.all([
    apiFetch<DashboardOverview>("/dashboard/overview"),
    apiFetch<TelegramLink>("/account-links/telegram"),
  ]);
  return <DashboardClient initialOverview={overview} initialTelegramLink={telegramLink} view={view} />;
}
