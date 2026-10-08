import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GovAuthProvider } from "../context/GovAuthContext";
import { GovAuthContext, useGovAuth } from "../context/useGovAuth";
import { Login } from "./Login";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

function ok(body) {
  return { ok: true, status: 200, json: async () => body };
}

function err(status, detail) {
  return { ok: false, status, json: async () => ({ detail }) };
}

function renderLogin() {
  return render(
    <MemoryRouter>
      <GovAuthProvider>
        <Login />
      </GovAuthProvider>
    </MemoryRouter>
  );
}

describe("government login", () => {
  it("renders the sign-in form with no public registration", () => {
    renderLogin();
    expect(screen.getByText("Government Sign In")).toBeTruthy();
    expect(screen.getByLabelText(/Employee ID/)).toBeTruthy();
    expect(screen.getByLabelText(/Password/)).toBeTruthy();
    expect(screen.queryByText(/register|sign up/i)).toBeNull();
    expect(screen.queryByText(/otp|forgot password|verify email/i)).toBeNull();
  });

  it("shows a generic error on invalid credentials", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => err(401, "Invalid credentials."))
    );
    renderLogin();
    fireEvent.change(screen.getByLabelText(/Employee ID/), {
      target: { value: "GOV-NOBODY-1" },
    });
    fireEvent.change(screen.getByLabelText(/Password/), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByText("Sign In"));
    await waitFor(() => {
      expect(screen.getByText("Invalid credentials.")).toBeTruthy();
    });
    expect(sessionStorage.getItem("gov_portal_session")).toBeNull();
  });

  it("stores the session on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        if (String(url).endsWith("/government/auth/login")) {
          return ok({ access_token: "govtok", token_type: "bearer" });
        }
        return ok({ id: "1", employee_id: "GOV-0001", is_active: true });
      })
    );
    renderLogin();
    fireEvent.change(screen.getByLabelText(/Employee ID/), {
      target: { value: "GOV-0001" },
    });
    fireEvent.change(screen.getByLabelText(/Password/), {
      target: { value: "correct-horse" },
    });
    fireEvent.click(screen.getByText("Sign In"));
    await waitFor(() => {
      expect(sessionStorage.getItem("gov_portal_session")).toContain("govtok");
    });
  });
});

describe("route protection", () => {
  it("redirects unauthenticated users to login", async () => {
    const { default: App } = await import("../App.jsx");
    render(
      <MemoryRouter initialEntries={["/"]}>
        <GovAuthProvider>
          <App />
        </GovAuthProvider>
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Government Sign In")).toBeTruthy();
    });
  });

  it("clears a rejected session and shows login", async () => {
    sessionStorage.setItem(
      "gov_portal_session",
      JSON.stringify({ access_token: "stale", token_type: "bearer" })
    );
    vi.stubGlobal("fetch", vi.fn(async () => err(401, "expired")));
    const { default: App } = await import("../App.jsx");
    render(
      <MemoryRouter initialEntries={["/"]}>
        <GovAuthProvider>
          <App />
        </GovAuthProvider>
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Government Sign In")).toBeTruthy();
    });
    expect(sessionStorage.getItem("gov_portal_session")).toBeNull();
  });

  it("logout clears the local session even when the API fails", async () => {
    sessionStorage.setItem(
      "gov_portal_session",
      JSON.stringify({ access_token: "t", token_type: "bearer" })
    );
    vi.stubGlobal("fetch", vi.fn(async () => err(500, "boom")));
    let logoutFn = null;
    function Probe() {
      logoutFn = useGovAuth().logout;
      return null;
    }
    render(
      <MemoryRouter>
        <GovAuthProvider>
          <Probe />
        </GovAuthProvider>
      </MemoryRouter>
    );
    await logoutFn();
    expect(sessionStorage.getItem("gov_portal_session")).toBeNull();
  });

  it("never exposes the token in rendered UI", () => {
    sessionStorage.setItem(
      "gov_portal_session",
      JSON.stringify({ access_token: "SECRET-TOKEN", token_type: "bearer" })
    );
    const { container } = render(
      <MemoryRouter>
        <GovAuthContext.Provider
          value={{
            official: { employee_id: "GOV-0001" },
            initializing: false,
            isAuthenticated: true,
          }}
        >
          <Login />
        </GovAuthContext.Provider>
      </MemoryRouter>
    );
    expect(container.textContent).not.toContain("SECRET-TOKEN");
  });
});
