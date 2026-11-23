import { expect, test } from "@playwright/test";

const liveEmail = process.env.E2E_EMPLOYEE_EMAIL;
const livePassword = process.env.E2E_EMPLOYEE_PASSWORD;

async function loginWithLiveCredentials(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(liveEmail!);
  await page.getByLabel("비밀번호").fill(livePassword!);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

test("unauthenticated users are redirected to login and see the memory-token notice", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: "직원 로그인" })).toBeVisible();
  await expect(page.getByText(/접속 토큰은 브라우저 저장소에 남기지 않습니다/)).toBeVisible();
  await expect(page.getByText(/보호된 화면입니다/)).toBeVisible();
});

test("live login covers dashboard, RAG readiness, and consultation gates", async ({ page }) => {
  test.skip(!liveEmail || !livePassword, "E2E_EMPLOYEE_EMAIL/E2E_EMPLOYEE_PASSWORD not configured; synthetic login bypass is not allowed.");
  await loginWithLiveCredentials(page);
  await expect(page.getByRole("heading", { name: "PB/WM 오늘의 업무 우선순위" })).toBeVisible();
  await expect(page.getByText(/AI 생성 ·/)).toBeVisible();
  await expect(page.getByText("국내 시장 데이터 상태")).toBeVisible();
  await expect(page.locator("body")).toContainText(/source_as_of/);

  await page.getByRole("link", { name: "RAG 질의응답" }).click();
  await expect(page).toHaveURL(/\/rag/);
  await expect(page.getByLabel("RAG readiness")).toBeVisible();
  await expect(page.getByText("데이터 준비 상태")).toBeVisible();
  await page.getByPlaceholder("ELS knock-in 후 고객 설명의무 범위").fill("ELS knock-in 후 고객 설명의무 범위");
  await page.getByRole("button", { name: "질문하기" }).click();
  await expect(page.getByText(/^AI 출력 /)).toBeVisible();
  await expect(page.getByText(/RAG 답변은 현재 차단/)).toBeVisible();
  await expect(page.getByText(/AI 생성 ·/)).toBeVisible();

  await page.getByRole("link", { name: "상담 워크스페이스" }).click();
  await expect(page).toHaveURL(/\/consultations\/new/);
  const completeButton = page.getByRole("button", { name: "상담 완료" });
  await expect(completeButton).toBeDisabled();
  await page.getByLabel("적합성 확인 완료").check();
  await expect(completeButton).toBeDisabled();
  await page.getByLabel("설명의무 확인 완료").check();
  await expect(completeButton).toBeEnabled();
  await expect(page.getByText("시뮬레이션 / 실제 주문 아님")).toBeVisible();
});
