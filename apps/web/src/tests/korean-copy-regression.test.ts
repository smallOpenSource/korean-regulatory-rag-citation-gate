import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { priorityLabel, statusLabel } from "../lib/labels";

const repoRoot = resolve(process.cwd(), "../..");
const COPY_TARGETS = [
  "apps/web/src",
  "docs/product",
  "docs/ui",
  "docs/business",
  "docs/frontend",
  "prompts",
] as const;

const STRICT_USER_COPY_TARGETS = ["docs/product", "docs/ui", "prompts"] as const;
const COPY_FILE_EXTENSIONS = new Set([".md", ".ts", ".tsx"]);
const ALLOWED_SOURCE_FILES = new Set([
  "apps/web/src/lib/labels.ts",
  "apps/web/src/lib/types.ts",
  "apps/web/src/components/Badges.tsx",
  "apps/web/src/tests/korean-copy-regression.test.ts",
]);

function extension(path: string): string {
  const lastDot = path.lastIndexOf(".");
  return lastDot === -1 ? "" : path.slice(lastDot);
}

function listFiles(path: string): string[] {
  const fullPath = join(repoRoot, path);
  if (!existsSync(fullPath)) {
    return [];
  }
  const stat = statSync(fullPath);
  if (stat.isFile()) {
    return COPY_FILE_EXTENSIONS.has(extension(fullPath)) ? [fullPath] : [];
  }
  return readdirSync(fullPath).flatMap((entry) => listFiles(join(path, entry)));
}

function readCopyFiles(paths: readonly string[]): Array<{ path: string; text: string }> {
  return paths
    .flatMap((path) => listFiles(path))
    .map((path) => ({ path: relative(repoRoot, path), text: readFileSync(path, "utf8") }));
}

describe("Korean-first user-facing copy", () => {
  it("keeps priority/status labels Korean at the label boundary", () => {
    expect(priorityLabel("URGENT")).toBe("긴급");
    expect(priorityLabel("HIGH")).toBe("높음");
    expect(priorityLabel("MEDIUM")).toBe("보통");
    expect(priorityLabel("LOW")).toBe("낮음");
    expect(statusLabel("DONE")).toBe("완료");
    expect(statusLabel("IN_PROGRESS")).toBe("진행 중");
  });

  it("rejects legacy English NBA inbox and synthetic placeholder display copy", () => {
    const bannedPatterns = [
      /URGENT NBA/i,
      /NBA Inbox/i,
      /Synthetic Portfolio/i,
      /SYN-CUST/i,
      /고객\s+[0-9]{1,2}\b/,
    ];
    const violations = readCopyFiles(COPY_TARGETS).flatMap(({ path, text }) => {
      if (ALLOWED_SOURCE_FILES.has(path)) {
        return [];
      }
      return bannedPatterns
        .filter((pattern) => pattern.test(text))
        .map((pattern) => `${path}: ${pattern}`);
    });

    expect(violations).toEqual([]);
  });

  it("keeps product/UI/prompt copy free of raw NBA, priority, and status jargon", () => {
    const rawUserCopyPattern =
      /\b(?:NBA|URGENT|HIGH|MEDIUM|LOW|PENDING|IN_PROGRESS|DONE|SNOOZED|DISMISSED|BLOCKED|APPROVED|READY)\b/;
    const violations = readCopyFiles(STRICT_USER_COPY_TARGETS)
      .filter(({ text }) => rawUserCopyPattern.test(text))
      .map(({ path }) => path);

    expect(violations).toEqual([]);
  });

  it("pairs source_as_of with the Korean 기준시각 label in rendered React copy", () => {
    const sourceFiles = readCopyFiles(["apps/web/src/pages", "apps/web/src/components"]);
    const violations = sourceFiles.flatMap(({ path, text }) => {
      const rawLabelViolations = [
        /label="source_as_of"/,
        /· source_as_of/,
        /source_as_of, freshness, quality/i,
      ]
        .filter((pattern) => pattern.test(text))
        .map((pattern) => `${path}: ${pattern}`);
      return rawLabelViolations;
    });

    expect(violations).toEqual([]);
  });

  it("keeps serviceable top200 readiness UI Korean and source-driven", () => {
    const sourceFiles = readCopyFiles([
      "apps/web/src/pages/BatchPage.tsx",
      "apps/web/src/pages/DashboardPage.tsx",
    ]);
    const combinedText = sourceFiles.map(({ text }) => text).join("\n");

    expect(combinedText).toContain("top200_coverage");
    expect(combinedText).toContain("시가총액 상위 200개 공식 KRX 커버리지");
    expect(combinedText).toContain("상위 200개 공식 KRX 커버리지");
    expect(combinedText).toContain("종목-거래일");
    expect(combinedText).toContain("KRX 기준시각");
    expect(combinedText).not.toMatch(/\b(?:DOMESTIC_TOP200_MARKET_CAP|OFFICIAL_KRX_APPROVED|PROVIDER_DONE)\b/);
  });

  it("keeps frontend tests free of mocked API readiness data", () => {
    const testFiles = readCopyFiles(["apps/web/src/tests"]);
    const mockApiPatterns = [
      /vi\.mock\(/,
      /vi\.mocked\(/,
      /mockResolvedValue/,
      /mockImplementation/,
      /jest\.mock\(/,
    ];
    const violations = testFiles.flatMap(({ path, text }) => {
      if (path === "apps/web/src/tests/korean-copy-regression.test.ts") {
        return [];
      }
      return mockApiPatterns
        .filter((pattern) => pattern.test(text))
        .map((pattern) => `${path}: ${pattern}`);
    });

    expect(violations).toEqual([]);
  });
});
