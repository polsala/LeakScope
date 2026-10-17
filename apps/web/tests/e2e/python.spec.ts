import { test, expect } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
const root = path.resolve("../..");
test("verified Python Lab source → exact allocation frames → report", async ({
  page,
  request,
}) => {
  test.skip(
    !existsSync(
      path.join(root, ".cache/python27/install-ucs4-lab/bin/python2.7"),
    ),
    "Build the genuine verified Lab interpreter first",
  );
  const token = readFileSync(
    path.join(root, "artifacts/e2e/admin.token"),
    "utf8",
  ).trim();
  const headers = { Authorization: `Bearer ${token}` };
  const started = await request.post("/fixture/python/start", { headers });
  expect(started.ok()).toBeTruthy();
  const { pid } = await started.json();
  await page.goto("/");
  await page.getByLabel("Credencial local").fill(token);
  await page.getByRole("button", { name: "Connecta", exact: true }).click();
  await page
    .getByRole("button", { name: "Diagnostica un procés", exact: true })
    .first()
    .click();
  await page
    .getByRole("textbox", { name: "Filtra per nom o PID…" })
    .fill(String(pid));
  await page
    .locator(`[data-pid="${pid}"]`)
    .getByRole("button", { name: "Diagnostica un procés" })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Continua" }).click();
  const lab = dialog.getByRole("button", { name: /Lab/ });
  await expect(lab).toBeEnabled();
  await lab.click();
  await dialog.getByRole("button", { name: "Continua" }).click();
  await dialog.getByRole("button", { name: "Inicia la captura" }).click();
  await expect(
    page.getByRole("button", { name: "Atura la captura" }),
  ).toBeVisible();
  const workload = await request.post("/fixture/python/run", { headers });
  expect((await workload.json()).held_objects).toBe(8);
  await page.getByRole("button", { name: "Atura la captura" }).click();
  await expect(
    page.getByText("CAPTURA FINALITZADA", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Flamegraph", exact: true }).click();
  await expect(page.getByLabel("Atribució", { exact: true })).toHaveValue(
    "python_exact_lines",
  );
  await expect(
    page.getByText(/Pila Python llegida al moment/).first(),
  ).toBeVisible();
  await page
    .getByLabel("Símbol", { exact: true })
    .fill("python_retention_site");
  await expect(page.locator(".native-site").first()).toHaveText(
    "python_retention_site",
  );
  await page
    .getByRole("checkbox", { name: "Supervivents", exact: true })
    .check();
  await expect(page.locator(".native-flame")).toBeVisible();
  await page.getByText("Cronologia d’operacions", { exact: true }).click();
  await expect(
    page.getByText("erp.cache_contract_data", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(root, "artifacts/python-lab-investigation.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: "Informes", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Sessió", exact: true })
    .selectOption({ index: 1 });
  await page
    .getByLabel("Títol de l’informe")
    .fill("Verified Python Lab evidence");
  await page
    .getByRole("button", { name: "Crea un informe", exact: true })
    .click();
  const card = page
    .locator(".report-card")
    .filter({ hasText: "Verified Python Lab evidence" })
    .first();
  const download = page.waitForEvent("download");
  await card.getByRole("button", { name: "Baixa HTML", exact: true }).click();
  const artifact = await download;
  const document = readFileSync((await artifact.path())!, "utf8");
  expect(document).toContain("python_retention_site");
  expect(document).toContain("Verified current Python frames");
});
