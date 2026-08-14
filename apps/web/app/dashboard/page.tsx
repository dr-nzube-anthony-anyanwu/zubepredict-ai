import { apiFetch } from "../../lib/api";
import type { DashboardOverview, TelegramLink } from "../../lib/types";
import DashboardClient from "./dashboard-client";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const [overview, telegramLink] = await Promise.all([
    apiFetch<DashboardOverview>("/dashboard/overview"),
    apiFetch<TelegramLink>("/account-links/telegram"),
  ]);
  return <DashboardClient initialOverview={overview} initialTelegramLink={telegramLink} />;
}
