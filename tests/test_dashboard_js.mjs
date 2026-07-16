import assert from "node:assert/strict";
import fs from "node:fs";

const html = fs.readFileSync(
  new URL("../docs/index.html", import.meta.url),
  "utf8",
);

const marker = "function buildColumns()";
const functionStart = html.indexOf(marker);
assert.notEqual(functionStart, -1, "Dashboard must define buildColumns()");

const bodyStart = html.indexOf("{", functionStart);
assert.notEqual(bodyStart, -1, "buildColumns() must have a function body");

let depth = 0;
let functionEnd = -1;
for (let index = bodyStart; index < html.length; index += 1) {
  if (html[index] === "{") depth += 1;
  if (html[index] === "}") depth -= 1;
  if (depth === 0) {
    functionEnd = index + 1;
    break;
  }
}
assert.notEqual(functionEnd, -1, "buildColumns() body must be balanced");

const buildColumnsSource = html.slice(functionStart, functionEnd);
const makeFormatter = () => () => "";
const buildColumns = new Function(
  "numFmt",
  "pctFmt",
  "okFmt",
  "makeSignalFormatter",
  "escHtml",
  `"use strict"; ${buildColumnsSource}; return buildColumns();`,
);

const columns = buildColumns(
  makeFormatter,
  () => "",
  () => "",
  makeFormatter,
  (value) => String(value),
);

assert.ok(Array.isArray(columns), "buildColumns() must return an array");
assert.ok(columns.length >= 60, "Dashboard should expose the complete column set");

const fields = new Set(columns.map((column) => column.field));
for (const requiredField of [
  "Ticker",
  "OverallScore",
  "Trap_Reasons",
  "DCF_Intrinsic_Value",
  "DCF_Data_Warning",
  "Valuation_Input_Warning",
]) {
  assert.ok(fields.has(requiredField), `Missing dashboard column: ${requiredField}`);
}

console.log(`Dashboard buildColumns() returned ${columns.length} columns`);
