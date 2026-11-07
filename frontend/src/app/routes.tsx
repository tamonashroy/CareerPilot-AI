import type { RouteObject } from "react-router";

import { AppShell } from "@/components/layout/app-shell";
import { NotFoundPage } from "@/pages/not-found-page";
import { StatusPage } from "@/pages/status-page";

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <StatusPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
