import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
const data = path.resolve("../../artifacts/kernel-e2e");
test("real kernel native profiling in the browser", async ({
  page,
  request,
}) => {
  const token = readFileSync(path.join(data, "admin.token"), "utf8");
  const pid = readFileSync(path.join(data, "fixture.pid"), "utf8");
  await page.goto("/");
  await page.getByLabel("Credencial local").fill(token);
  await page.getByRole("button", { name: "Connecta", exact: true }).click();
  await page
    .getByRole("button", { name: "Diagnostica un procés", exact: true })
    .first()
    .click();
  await page.getByRole("textbox", { name: "Filtra per nom o PID…" }).fill(pid);
  await page
    .locator(`[data-pid="${pid}"]`)
    .getByRole("button", { name: "Diagnostica un procés" })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Continua" }).click();
  await dialog.getByRole("button", { name: "Continua" }).click();
  await dialog
    .getByLabel("Activa sondes natives (malloc/calloc/realloc/free)")
    .check();
  await dialog.getByLabel("Durada (segons)").fill("30");
  await dialog.getByRole("button", { name: "Inicia la captura" }).click();
  await expect(
    page.getByRole("button", { name: "Atura la captura" }),
  ).toBeVisible();
  const truth = await (await request.post("/fixture/allocate")).json();
  expect(truth.bytes).toBe(3145728);
  await page.getByRole("tab", { name: "Flamegraph", exact: true }).click();
  await page
    .getByLabel("Biblioteca", { exact: true })
    .fill("libgroundtruth.so");
  await expect(
    page
      .getByRole("button", { name: "leakscope_leak_site", exact: true })
      .first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Atura la captura" }).click();
  await expect(
    page.getByText("CAPTURA FINALITZADA", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".native-view .native-totals")).toContainText(
    "3.0 MiB",
  );
  await page
    .getByRole("checkbox", { name: "Supervivents", exact: true })
    .check();
  await page
    .getByRole("checkbox", { name: "Vista de caramells", exact: true })
    .check();
  await page.getByRole("tab", { name: "Arbre de crides", exact: true }).click();
  await expect(page.locator(".native-calltree").first()).toContainText(
    "leakscope_leak_site",
  );
  await page.screenshot({
    path: "../../artifacts/kernel/browser-native.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "Informes", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Sessió", exact: true })
    .selectOption({ index: 1 });
  await page.getByLabel("Títol de l’informe").fill("Real native leak");
  await page.getByRole("button", { name: "Crea un informe" }).click();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Baixa HTML" }).first().click(),
  ]);
  const html = readFileSync((await download.path())!, "utf8");
  expect(html).toContain("leakscope_leak_site");
  expect(html).toContain("Native allocation flamegraph");
});
