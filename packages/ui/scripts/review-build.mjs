import { build } from "esbuild";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { posix, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = fileURLToPath(new URL("..", import.meta.url));
const require = createRequire(import.meta.url);
export async function buildReview() {
  const manifest = JSON.parse(await readFile(new URL("../review/sources.json", import.meta.url), "utf8"));
  const trees = new Map(); const cache = new Map(); const inputHashes = {};
  for (const [key, source] of Object.entries(manifest.pages)) {
    if (!/^[a-f0-9]{40}$/.test(source.commit)) throw new Error(`Unpinned UI source: ${key}`);
    const names = execFileSync("git", ["ls-tree", "--full-tree", "-r", "--name-only", source.commit, "--", ...source.prefixes], { cwd: packageRoot, encoding: "utf8" }).trim().split("\n");
    trees.set(key, new Set(names));
  }
  function resolveSource(key, path) {
    const source = manifest.pages[key];
    if (!source || !source.prefixes.some(prefix => path.startsWith(prefix))) throw new Error(`UI import outside approved page: ${key}/${path}`);
    const candidates = [path, ...[".tsx", ".ts", ".jsx", ".js", ".json", ".css"].map(ext => `${path}${ext}`), `${path}/index.tsx`, `${path}/index.ts`];
    const match = candidates.find(candidate => trees.get(key).has(candidate));
    if (!match) throw new Error(`Missing pinned UI source: ${key}/${path}`);
    return { path: `${key}/${match}`, namespace: "approved-ui" };
  }
  const plugin = { name: "approved-final-ui", setup(context) {
    context.onResolve({ filter: /^final-ui:/ }, args => { const key = args.path.slice(9); return resolveSource(key, manifest.pages[key]?.entry ?? ""); });
    context.onResolve({ filter: /^@ikun\/ui$/ }, () => ({ path: "shared-ui-bridge", namespace: "review-bridge" }));
    context.onResolve({ filter: /^@ikun\/ui\/styles\.css$/ }, () => ({ path: resolve(packageRoot, "src/styles.css") }));
    context.onLoad({ filter: /.*/, namespace: "review-bridge" }, () => ({ contents: `export * from ${JSON.stringify(resolve(packageRoot, "src/index.ts"))}; export {EmbeddedAppShell as AppShell} from ${JSON.stringify(resolve(packageRoot, "review/embedded-shell.tsx"))};`, loader: "ts", resolveDir: packageRoot }));
    context.onResolve({ filter: /.*/, namespace: "approved-ui" }, args => {
      const slash = args.importer.indexOf("/"); const key = args.importer.slice(0, slash); const path = args.importer.slice(slash + 1);
      if (args.path.startsWith(".")) return resolveSource(key, posix.normalize(posix.join(posix.dirname(path), args.path)));
      if (/^(react|react-dom)(\/|$)/.test(args.path)) return { path: require.resolve(args.path) };
      throw new Error(`Unexpected dependency in approved UI: ${args.path}`);
    });
    context.onLoad({ filter: /.*/, namespace: "approved-ui" }, async args => {
      const slash = args.path.indexOf("/"); const key = args.path.slice(0, slash); const path = args.path.slice(slash + 1); const source = manifest.pages[key];
      if (!cache.has(args.path)) cache.set(args.path, execFileSync("git", ["show", `${source.commit}:${path}`], { cwd: packageRoot, maxBuffer: 4 * 1024 * 1024 }));
      const contents = cache.get(args.path);
      const { createHash } = await import("node:crypto"); inputHashes[args.path] = createHash("sha256").update(contents).digest("hex");
      const loader = path.endsWith(".module.css") ? "local-css" : path.endsWith(".css") ? "css" : path.endsWith(".json") ? "json" : path.endsWith(".tsx") ? "tsx" : path.endsWith(".ts") ? "ts" : "jsx";
      return { contents, loader };
    });
  } };
  const result = await build({ entryPoints: [resolve(packageRoot, "review/main.tsx")], bundle: true, write: false, outdir: "review-output", platform: "browser", format: "esm", jsx: "automatic", target: ["es2022"], plugins: [plugin], define: { "process.env.NODE_ENV": '"development"' }, sourcemap: "inline", logLevel: "warning" });
  const js = result.outputFiles.find(file => file.path.endsWith(".js"))?.contents;
  const css = result.outputFiles.find(file => file.path.endsWith(".css"))?.contents;
  if (!js || !css) throw new Error("Review assets missing");
  return { js, css, manifest, inputHashes, warnings: result.warnings.map(w => w.text) };
}
