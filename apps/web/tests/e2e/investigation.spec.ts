import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
const data = path.resolve("../../artifacts/e2e");
test("real Python 2 process → capture → compare → offline report", async ({
  page,
}) => {
  const token = readFileSync(path.join(data, "admin.token"), "utf8");
  const pid = readFileSync(path.join(data, "fixture.pid"), "utf8");
  await page.goto("/");
  await page.getByLabel("Credencial local").fill(token);
  await page.getByRole("button", { name: "Connecta", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "La memòria, amb context." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Diagnostica un procés", exact: true })
    .first()
    .click();
  await page.getByRole("textbox", { name: "Filtra per nom o PID…" }).fill(pid);
  const row = page.locator(`[data-pid="${pid}"]`);
  await expect(row).toBeVisible();
  await expect(row).toContainText("2.7");
  await row.getByRole("button", { name: "Diagnostica un procés" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Continua" }).click();
  await expect(dialog).toContainText("No disponible");
  await dialog.getByRole("button", { name: "Continua" }).click();
  await dialog.getByLabel("Durada (segons)").fill("30");
  await dialog.getByLabel("Interval (ms)").fill("200");
  await dialog.getByRole("button", { name: "Inicia la captura" }).click();
  await expect(
    page.getByRole("button", { name: "Atura la captura" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Evolució de la memòria/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Afegeix una marca" }).click();
  await page
    .getByRole("textbox", { name: "Nom de la marca" })
    .fill("baseline A");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Desa els canvis" })
    .click();
  await expect(page.locator(".marker-list")).toContainText("baseline A");
  await page.getByRole("button", { name: "Atura la captura" }).click();
  await expect(
    page.getByText("CAPTURA FINALITZADA", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Exporta la captura" }),
  ).toBeVisible();
  const [capture] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Exporta la captura" }).click(),
  ]);
  const capturedPath = await capture.path();
  expect(readFileSync(capturedPath!).subarray(0, 8).toString("hex")).toBe(
    "4c53434150000100",
  );
  await page.getByRole("button", { name: "Compara les dues meitats" }).click();
  await expect(
    page.getByRole("heading", { name: "Comparacions", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".comparison").first()).toBeVisible();
  await page.getByRole("link", { name: "Informes", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Informes", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Sessió", exact: true })
    .selectOption({ index: 1 });
  await page
    .getByRole("textbox", { name: "Títol de l’informe" })
    .fill("Fixture investigation");
  await page
    .getByRole("textbox", { name: "Passos de reproducció" })
    .fill("Run leak_global_list.py and sample its RSS.");
  await page.getByRole("button", { name: "Crea un informe" }).click();
  await expect(
    page.getByRole("heading", { name: "Fixture investigation" }).first(),
  ).toBeVisible();
  const [report] = await Promise.all([
    page.waitForEvent("download"),
    page
      .locator(".report-card")
      .filter({ hasText: "Fixture investigation" })
      .first()
      .getByRole("button", { name: "Baixa HTML" })
      .click(),
  ]);
  const html = readFileSync((await report.path())!, "utf8");
  expect(html).toContain("Fixture investigation");
  expect(html).toContain("<svg");
  expect(html).toContain("RSS growth");
  await page.screenshot({
    path: "../../artifacts/overview-report.png",
    fullPage: true,
  });
});
test("keyboard navigation, languages and small screen", async ({ page }) => {
  const token = readFileSync(path.join(data, "admin.token"), "utf8");
  await page.goto("/");
  await page.getByLabel("Credencial local").fill(token);
  await page.getByRole("button", { name: "Connecta", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "La memòria, amb context." }),
  ).toBeVisible();
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("combobox", { name: "Idioma" }).selectOption("en");
  await expect(
    page.getByRole("heading", { name: "Memory, in context." }),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "Language" }).selectOption("es");
  await expect(
    page.getByRole("heading", { name: "La memoria, con contexto." }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "../../artifacts/mobile-overview.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
