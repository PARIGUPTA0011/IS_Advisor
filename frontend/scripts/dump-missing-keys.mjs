// One-off: for every supported language (except en), find which en.json leaf
// keys have no translation yet (hi.json's own keys, or indic.ts's
// translationFor() output, for everyone else), and dump {code: {key: englishText}}
// so a separate (Python) script can batch-translate them through the project's
// own NLLB translator and mark the result as machine-generated.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const ts = require("typescript");
const english = JSON.parse(fs.readFileSync(path.join(root, "src/i18n/en.json"), "utf8"));
const hindi = JSON.parse(fs.readFileSync(path.join(root, "src/i18n/hi.json"), "utf8"));
const generated = JSON.parse(fs.readFileSync(path.join(root, "src/i18n/generated.json"), "utf8"));
const indexSource = fs.readFileSync(path.join(root, "src/i18n/index.ts"), "utf8");
const codesBlock = indexSource.match(/SUPPORTED_LANGUAGE_CODES\s*=\s*\[([\s\S]*?)\]/)?.[1] ?? "";
const codes = [...codesBlock.matchAll(/"([a-z]{2,3})"/g)].map((m) => m[1]).filter((c) => c !== "en");

const indicSource = fs.readFileSync(path.join(root, "src/i18n/indic.ts"), "utf8");
const compiled = ts.transpileModule(indicSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exportsObj = {};
new Function("exports", "module", compiled)(exportsObj, { exports: exportsObj });

function leaves(value, prefix = "") {
  if (!value || typeof value !== "object" || Array.isArray(value)) return prefix ? [[prefix, value]] : [];
  return Object.entries(value).flatMap(([key, child]) =>
    leaves(child, prefix ? `${prefix}.${key}` : key),
  );
}
function atPath(value, dottedPath) {
  return dottedPath.split(".").reduce((node, key) => (node && typeof node === "object" ? node[key] : undefined), value);
}

function deepMerge(base, override) {
  if (base && override && typeof base === "object" && typeof override === "object" &&
      !Array.isArray(base) && !Array.isArray(override)) {
    const merged = { ...base };
    for (const [key, value] of Object.entries(override)) {
      if (value === undefined) continue;
      merged[key] = key in merged ? deepMerge(merged[key], value) : value;
    }
    return merged;
  }
  return override;
}

const englishLeaves = leaves(english);
const out = {};
for (const code of codes) {
  const handWritten = code === "hi" ? hindi : exportsObj.translationFor(code);
  const machineTranslated = generated[code];
  const resource = machineTranslated ? deepMerge(machineTranslated, handWritten) : handWritten;
  const missing = {};
  for (const [key, value] of englishLeaves) {
    if (atPath(resource, key) === undefined) missing[key] = value;
  }
  if (Object.keys(missing).length) out[code] = missing;
}

fs.writeFileSync(path.join(root, "scripts/missing-keys.json"), JSON.stringify(out, null, 2), "utf8");
console.log(`wrote scripts/missing-keys.json: ${Object.keys(out).length} languages, ` +
  `${Object.values(out).reduce((n, m) => n + Object.keys(m).length, 0)} total missing strings`);
