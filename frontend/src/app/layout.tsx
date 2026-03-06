import type { Metadata } from "next";
import AuthProvider from "@/components/AuthProvider";
import ShellWrapper from "@/components/ShellWrapper";
import "./globals.css";

export const metadata: Metadata = {
  title: "IdeaScope",
  description: "Solo bootstrapper idea validation pipeline",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body
        className="bg-gray-950 text-gray-100 antialiased"
        style={{ fontFamily: "'DM Sans', sans-serif" }}
      >
        <AuthProvider>
          <ShellWrapper>{children}</ShellWrapper>
        </AuthProvider>
      </body>
    </html>
  );
}
