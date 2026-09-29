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
const codes = [...codesBlock.matchAll(/"([a-z]{2,3})"/g)].map((match) => match[1]);

const indicSource = fs.readFileSync(path.join(root, "src/i18n/indic.ts"), "utf8");
const compiled = ts.transpileModule(indicSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exports = {};
new Function("exports", "module", compiled)(exports, { exports });

function leaves(value, prefix = "") {
  if (!value || typeof value !== "object" || Array.isArray(value)) return prefix ? [prefix] : [];
  return Object.entries(value).flatMap(([key, child]) => leaves(child, prefix ? `${prefix}.${key}` : key));
}

function atPath(value, dottedPath) {
  return dottedPath.split(".").reduce((node, key) => node && typeof node === "object" ? node[key] : undefined, value);
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

const errors = [];
const englishKeys = leaves(english);
for (const code of codes) {
  const handWritten = code === "en" ? english : code === "hi" ? hindi : exports.translationFor(code);
  const machineTranslated = generated[code];
  const resource = machineTranslated ? deepMerge(machineTranslated, handWritten) : handWritten;
  for (const key of englishKeys) {
    if (atPath(resource, key) === undefined) errors.push(`missing ${code}:${key}`);
  }
}

const sourceRoot = path.join(root, "src");
function inspectTsx(file) {
  const sourceText = fs.readFileSync(file, "utf8");
  const sourceFile = ts.createSourceFile(file, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  function visit(node) {
    if (ts.isJsxText(node)) {
      const text = node.getText(sourceFile).replace(/\s+/g, " ").trim();
      if (/[A-Za-z]{3,}/.test(text)) {
        errors.push(`hardcoded JSX text ${path.relative(sourceRoot, file)}:${sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1}: ${JSON.stringify(text)}`);
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
}

function walk(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(fullPath);
    else if (entry.name.endsWith(".tsx")) inspectTsx(fullPath);
  }
}
walk(sourceRoot);

if (errors.length) {
  console.error(`i18n check failed with ${errors.length} issue(s):`);
  for (const error of errors) console.error(`- ${error}`);
  process.exitCode = 1;
} else {
  console.log(`i18n check passed: ${codes.length} locales contain every English key; no JSX text literals found.`);
}