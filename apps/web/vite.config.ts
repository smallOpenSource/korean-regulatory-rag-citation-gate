import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import crypto from "crypto";
import { promises as fs } from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { loadEnv } from "vite";
import { Plugin, defineConfig } from "vitest/config";

/**
 * Inline SRI plugin (REG-05 T285).
 *
 * Computes SHA-384 hashes from ON-DISK files in writeBundle (post-write),
 * so post-process steps (vite finalization, etc.) do not invalidate the hash.
 * Then re-reads index.html, patches <script src> / <link href> tags with
 * `integrity="sha384-..."` + `crossorigin="anonymous"`, and writes it back.
 *
 * No external package required — uses Node.js built-in `crypto` and `fs`.
 * Verify output with: scripts/verify_vite_sri.sh apps/web/dist/index.html
 */
function sriPlugin(): Plugin {
  return {
    name: "harness-sri",
    enforce: "post",
    apply: "build",

    async writeBundle(options, bundle) {
      const outDir = options.dir ?? "dist";
      const integrityMap = new Map<string, string>();

      for (const fileName of Object.keys(bundle)) {
        if (!/\.(js|css)$/.test(fileName)) continue;
        const filePath = path.join(outDir, fileName);
        const content = await fs.readFile(filePath);
        const hash = crypto.createHash("sha384").update(content).digest("base64");
        integrityMap.set(fileName, `sha384-${hash}`);
      }

      for (const fileName of Object.keys(bundle)) {
        if (!fileName.endsWith(".html")) continue;
        const htmlPath = path.join(outDir, fileName);
        let html = await fs.readFile(htmlPath, "utf-8");

        for (const [file, integrity] of integrityMap) {
          const escaped = file.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

          html = html.replace(
            new RegExp(
              `(<script\\b[^>]*\\bsrc=["'][^"']*${escaped}["'][^>]*?)(?:\\s+integrity=["'][^"']*["'])?(?:\\s+crossorigin=["'][^"']*["'])?(>)`,
              "gi"
            ),
            `$1 integrity="${integrity}" crossorigin="anonymous"$2`
          );

          html = html.replace(
            new RegExp(
              `(<link\\b[^>]*\\bhref=["'][^"']*${escaped}["'][^>]*?)(?:\\s+integrity=["'][^"']*["'])?(?:\\s+crossorigin=["'][^"']*["'])?(>)`,
              "gi"
            ),
            `$1 integrity="${integrity}" crossorigin="anonymous"$2`
          );
        }

        await fs.writeFile(htmlPath, html, "utf-8");
      }
    },
  };
}

// Dev-server port의 단일 SoT는 repo-root `.env`의 HARNESS_WEB_PORT 다.
// loadEnv 가 cwd 와 무관하게 repo-root `.env` 를 읽으므로 `npm run dev` 직접
// 실행도 `.env` 를 따른다. scripts/start.sh 는 추가로 `--port $(web_port)` 를
// 넘기며, vite 에서 CLI 플래그는 항상 이 config 값보다 우선한다.
export default defineConfig(({ mode }) => {
  const repoRoot = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "../.."
  );
  const rootEnv = loadEnv(mode, repoRoot, "");
  const webPort =
    Number(process.env.HARNESS_WEB_PORT ?? rootEnv.HARNESS_WEB_PORT) || 5173;
  // 프록시 백엔드 타깃 포트의 단일 SoT도 repo-root `.env`의 HARNESS_API_PORT 다.
  // HARNESS_E2E_API_TARGET 가 설정되면 그것이 우선한다(e2e 전용 명시 override).
  const apiPort =
    Number(process.env.HARNESS_API_PORT ?? rootEnv.HARNESS_API_PORT) || 8000;
  const apiProxy = {
    target:
      process.env.HARNESS_E2E_API_TARGET ?? `http://127.0.0.1:${apiPort}`,
    changeOrigin: false,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
    ws: true,
  };

  return {
    plugins: [react(), tailwindcss(), sriPlugin()],
    server: {
      port: webPort,
      strictPort: true,
      proxy: {
        "/api": apiProxy,
      },
    },
    preview: {
      port: 4173,
      strictPort: true,
      proxy: {
        "/api": apiProxy,
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/tests/setup.ts",
      exclude: ["e2e/**", "node_modules/**", "dist/**"],
    },
  };
});
