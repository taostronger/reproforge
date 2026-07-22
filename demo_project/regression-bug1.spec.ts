import { test, expect } from '@playwright/test';

/**
 * Bug1 回归验证闭环（同一断言：total-price 应为 160）。
 *   buggy（默认）: apply SALE20 后改数量 2，total 仍 80（不重算）→ 断言 160 失败 = 复现 Bug
 *   fixed (?fixed=1): total 实时重算 = 200*0.8 = 160 → 断言 160 通过 = 回归验证
 * 同一测试，buggy 版失败、fixed 版通过 —— 最强的"证明闭环"。
 */
test('buggy: coupon not recalculated on qty change -> expect 160 fails (actual 80)', async ({ page }) => {
  await page.goto('http://localhost:5173/');
  await page.getByTestId('coupon-input').fill('SALE20');
  await page.getByTestId('apply-btn').click();
  await page.getByTestId('qty-input').fill('2');
  await expect(page.getByTestId('total-price')).toHaveText('160');
});

test('fixed (?fixed=1): recalc on qty change -> expect 160 passes (actual 160)', async ({ page }) => {
  await page.goto('http://localhost:5173/?fixed=1');
  await page.getByTestId('coupon-input').fill('SALE20');
  await page.getByTestId('apply-btn').click();
  await page.getByTestId('qty-input').fill('2');
  await expect(page.getByTestId('total-price')).toHaveText('160');
});
