import { test, expect } from '@playwright/test';

// UI/UX smoke для одностраничника. Сетевые проверки помечены @network
// (тайлы OSM/НСПД требуют сети) и могут быть пропущены: --grep-invert @network.

test('boots and shows v2.9.62', async ({ page }) => {
  await page.goto('/index.html');
  await expect(page).toHaveTitle(/2\.9\.62/);
  await expect(page.locator('#app')).toBeVisible();
  await expect(page.locator('#logo')).toContainText('2.9.62');
});

test('version switcher banner links to frozen page', async ({ page }) => {
  await page.goto('/index.html');
  const link = page.locator('#ver-switch a');
  await expect(link).toHaveAttribute('href', './v2961.html');
  await page.goto('/v2961.html');
  await expect(page.locator('#ver-switch a')).toHaveAttribute('href', './index.html');
});

test('map container renders', async ({ page }) => {
  await page.goto('/index.html');
  await expect(page.locator('.leaflet-container')).toBeVisible();
});

test('@network base tiles load', async ({ page }) => {
  await page.goto('/index.html');
  await expect(page.locator('img.leaflet-tile').first()).toBeVisible({ timeout: 15_000 });
});

test('upload menu opens with import-tiles item', async ({ page }) => {
  await page.goto('/index.html');
  await page.locator('#upload-btn').click();
  const menu = page.locator('#upload-menu');
  await expect(menu).toBeVisible();
  await expect(menu).toContainText('Загрузить чужие тайлы z17');
});

test('export menu builds with cadastre-tiles item', async ({ page }) => {
  await page.goto('/index.html');
  await page.locator('#export-btn').click();
  const menu = page.locator('#export-menu');
  await expect(menu).toHaveClass(/open/);
  await expect(menu).toContainText('Выгрузить как');
  await expect(menu).toContainText('Выгрузить тайлы Росреестра z17');
});

test('cadastre toggle activates the layer button', async ({ page }) => {
  await page.goto('/index.html');
  await page.locator('#cadastre-btn').click();
  // открытие dropdown при !cadastreActive само вызывает _applyCadastreLayers
  await expect(page.locator('#cadastre-btn')).toHaveClass(/active/, { timeout: 8_000 });
});

test('KML parse+dedup is idempotent for identical input', async ({ page }) => {
  await page.goto('/index.html');
  const dup = await page.evaluate(() => {
    // @ts-ignore — функции приложения в глобальной области
    if (typeof parseKML !== 'function' || typeof _dedupParsedPlacemarks !== 'function') return 'skip';
    const kml = `<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>t</name>` +
      `<Placemark><name>77:01:0001001:1</name><Point><coordinates>37.6,55.7,0</coordinates></Point></Placemark>` +
      `</Document></kml>`;
    // @ts-ignore
    const a = parseKML(kml, 'a.kml'); _dedupParsedPlacemarks(a, 'a.kml');
    // @ts-ignore
    const b = parseKML(kml, 'b.kml'); const n = _dedupParsedPlacemarks(b, 'b.kml');
    return n;
  });
  if (dup === 'skip') test.skip(true, 'app dedup API not exposed globally');
  expect(Number(dup)).toBeGreaterThan(0); // второй идентичный набор подавлен
});
