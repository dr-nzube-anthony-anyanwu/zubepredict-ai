import type { Metadata } from "next";
import DashboardRoute from "../dashboard-page";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Projects", description: "Organise questions and privately validated datasets for governed experiments." };

export default function ProjectsPage() {
  return <DashboardRoute view="projects" />;
}
