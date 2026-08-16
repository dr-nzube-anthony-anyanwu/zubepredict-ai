import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: {
    default: "ZubePredict AI — From raw data to defensible decisions",
    template: "%s | ZubePredict AI",
  },
  description: "A governed autonomous data-science platform that turns organisational data and real-world questions into reproducible, decision-ready evidence.",
  keywords: ["autonomous data science", "machine learning", "evidence reports", "eye care analytics", "predictive intelligence"],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
