import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { THEME_STORAGE_KEY, resolveInitialTheme } from "@/components/theme/theme";
import { renderRoute } from "@/test/render";

function mockSystemTheme(prefersDark: boolean) {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: prefersDark }));
}

describe("routing", () => {
  it("shows the 404 page for an unknown path and links home", () => {
    renderRoute("/no-such-page");
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to system status" })).toHaveAttribute(
      "href",
      "/",
    );
  });
});

describe("theme", () => {
  it("follows the system setting when nothing is saved", () => {
    mockSystemTheme(true);
    expect(resolveInitialTheme()).toBe("dark");
    mockSystemTheme(false);
    expect(resolveInitialTheme()).toBe("light");
  });

  it("prefers a saved choice over the system setting", () => {
    mockSystemTheme(true);
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    expect(resolveInitialTheme()).toBe("light");
  });

  it("toggles the page theme and saves the choice", async () => {
    mockSystemTheme(false);
    renderRoute("/no-such-page");
    expect(document.documentElement).not.toHaveClass("dark");

    await userEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement).toHaveClass("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    await userEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));
    expect(document.documentElement).not.toHaveClass("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("still works when storage is blocked", async () => {
    mockSystemTheme(false);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    renderRoute("/no-such-page");
    await userEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement).toHaveClass("dark");
  });
});
