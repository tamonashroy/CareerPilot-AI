import { Link, Outlet } from "react-router";

import { ThemeToggle } from "@/components/theme/theme-toggle";

export function AppShell() {
  return (
    <div className="min-h-screen">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-3xl items-center justify-between px-4">
          <Link to="/" className="font-semibold">
            CareerPilot AI
          </Link>
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
