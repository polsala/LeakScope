import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
test("continuous metrics → independent-window safety → findings and manual phases", async ({
  page,
  request,
}) => {
  const root = path.resolve("../..");
  const token = readFileSync(
    path.join(root, "artifacts/e2e/admin.token"),
    "utf8",
  ).trim();
  const pid = Number(
    readFileSync(path.join(root, "artifacts/e2e/fixture.pid"), "utf8"),
  );
  const headers = { Authorization: `Bearer ${token}` };
  await page.goto("/");
  await page.getByLabel("Credencial local").fill(token);
  await page.getByRole("button", { name: "Connecta", exact: true }).click();
  const host = (await (await request.get("/api/v1/hosts", { headers })).json())
    .items[0].id;
  const processes = (
    await (
      await request.get(`/api/v1/hosts/${host}/processes?limit=2000`, {
        headers,
      })
    ).json()
  ).items;
  const process = processes.find((p: { pid: number }) => p.pid === pid);
  await page.getByRole("link", { name: "Monitoratge", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Observació contínua", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Processos", exact: true })
    .selectOption(process.key);
  await expect(
    page.getByLabel(/Autoritzo captures natives automàtiques/),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Inicia el monitoratge", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Atura el monitoratge", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Evolució de la memòria:/ }).first(),
  ).toBeVisible();
  await expect(
    page.getByText(/no se sumen supervivents entre buits/),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Atura el monitoratge", exact: true })
    .click();
  const response = await request.post("/api/v1/sessions", {
    headers,
    data: {
      process_key: process.key,
      duration_seconds: 30,
      sample_interval_ms: 100,
    },
  });
  expect(response.ok()).toBeTruthy();
  const session = await response.json();
  await page.goto(`/#/findings/${session.id}`);
  await expect(
    page.getByRole("heading", { name: "Troballes", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Operació", { exact: true })
    .fill("fixture.manual_boundary");
  await page
    .getByRole("button", { name: "Configura l’experiment", exact: true })
    .click();
  for (const label of [
    "Base A",
    "Repeticions",
    "Inici del refredament",
    "Comparació B",
  ]) {
    const button = page.getByRole("button", { name: label, exact: true });
    await expect(button).toBeEnabled();
    await button.click();
    await expect(
      page.locator("li").filter({ hasText: label }).first(),
    ).toBeVisible();
  }
  await expect(page.getByText(/no executa mètodes de negoci/)).toBeVisible();
  await request.post(`/api/v1/sessions/${session.id}/stop`, { headers });
  await page.screenshot({
    path: path.join(root, "artifacts/production-monitoring-findings.png"),
    fullPage: true,
  });
  const points = (
    await (
      await request.get(`/api/v1/sessions/${session.id}/timeline`, { headers })
    ).json()
  ).items;
  expect(points.length).toBeGreaterThan(1);
  const start = points[0].timestamp,
    end = points.at(-1).timestamp,
    middle = (start + end) / 2;
  await page
    .getByRole("spinbutton", { name: "A Inicia la captura", exact: true })
    .fill(String(start));
  await page
    .getByRole("spinbutton", { name: "A Final", exact: true })
    .fill(String(middle));
  await page
    .getByRole("spinbutton", { name: "B Inicia la captura", exact: true })
    .fill(String(middle));
  await page
    .getByRole("spinbutton", { name: "B Final", exact: true })
    .fill(String(end));
  await page.getByRole("button", { name: "Compara", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Comparacions", exact: true }),
  ).toBeVisible();
});
