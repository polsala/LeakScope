import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

test("login and deployment health expose accessible controls", async ({
  page,
}) => {
  await page.goto("/");
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  const token = readFileSync(
    path.resolve("../../artifacts/e2e/admin.token"),
    "utf8",
  );
  await page.getByLabel("Credencial local").fill(token);
  await page.getByRole("button", { name: "Connecta", exact: true }).click();
  await page.getByRole("link", { name: "Configuració", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Salut del desplegament" }),
  ).toBeVisible();
  await expect(
    page.getByText("Estat de la base de dades:", { exact: false }),
  ).toBeVisible();
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations).toEqual([]);
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toHaveCount(1);
});
