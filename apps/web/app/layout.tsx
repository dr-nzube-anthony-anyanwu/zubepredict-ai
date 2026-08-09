import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "ZubePredict AI",
  description: "An autonomous, evidence-driven data-science workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
