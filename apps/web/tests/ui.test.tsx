import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { dictionaries, ca } from "../src/i18n";
import { useUI } from "../src/store";
import { bytes } from "../src/api";
import { Capability, Empty, Failure, Modal } from "../src/components";
import App from "../src/App";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  useUI.setState({ token: "", locale: "ca" });
});
describe("user-facing evidence", () => {
  it("has complete Catalan, Spanish and English catalogs", () => {
    for (const language of Object.values(dictionaries)) {
      expect(Object.keys(language).sort()).toEqual(Object.keys(ca).sort());
      expect(Object.values(language).every((v) => v.trim())).toBe(true);
    }
  });
  it("does not represent unknown bytes as zero", () => {
    expect(bytes(null)).toBe("—");
    expect(bytes(0)).toBe("0 B");
    expect(bytes(1024)).toBe("1.0 KiB");
    expect(bytes(-1024)).toBe("-1.0 KiB");
  });
  it("makes observation limitations visible", () => {
    render(<Capability />);
    expect(screen.getByText(ca.capabilityBody)).toBeVisible();
  });
  it("supports empty and failure states", () => {
    render(
      <>
        <Empty title={ca.noSessions} />
        <Failure error={new Error("Collector disconnected")} />
      </>,
    );
    expect(screen.getByText(ca.noSessions)).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Collector disconnected",
    );
  });
  it("uses an accessible keyboard-dismissable dialog", () => {
    const close = vi.fn();
    render(
      <Modal title="Test dialog" close={close}>
        <button>Action</button>
      </Modal>,
    );
    expect(screen.getByRole("dialog", { name: "Test dialog" })).toBeVisible();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(close).toHaveBeenCalled();
  });
  it("starts with a working Catalan credential form", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <App />
      </QueryClientProvider>,
    );
    expect(screen.getByRole("button", { name: ca.connect })).toBeVisible();
    expect(screen.getByLabelText(ca.token)).toHaveAttribute("type", "password");
    expect(document.documentElement.lang).toBe("ca");
  });
});
