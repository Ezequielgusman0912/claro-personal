import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = join(root, "static", "registro", "vendor", "ocr");
const spaPackage = dirname(require.resolve("@tesseract.js-data/spa/package.json"));
const corePackage = dirname(require.resolve("tesseract.js-core/package.json"));
const tesseractPackage = dirname(require.resolve("tesseract.js/package.json"));

await mkdir(join(output, "lang"), { recursive: true });
const files = [
  [join(tesseractPackage, "dist", "tesseract.min.js"), "tesseract.min.js"],
  [join(tesseractPackage, "dist", "tesseract.min.js.LICENSE.txt"), "tesseract.LICENSE.txt"],
  [join(tesseractPackage, "dist", "worker.min.js"), "worker.min.js"],
  [join(corePackage, "tesseract-core-simd-lstm.wasm.js"), "tesseract-core-simd-lstm.wasm.js"],
  [join(corePackage, "LICENSE"), "tesseract-core.LICENSE"],
  [join(spaPackage, "4.0.0_best_int", "spa.traineddata.gz"), join("lang", "spa.traineddata.gz")],
];

for (const [source, relativeDestination] of files) {
  const destination = join(output, relativeDestination);
  await mkdir(dirname(destination), { recursive: true });
  if (relativeDestination.endsWith(".min.js")) {
    const contents = await readFile(source, "utf8");
    const withoutSourceMap = contents.replace(/\n\/\/# sourceMappingURL=[^\s]+\s*$/, "");
    await writeFile(destination, withoutSourceMap);
  } else {
    await copyFile(source, destination);
  }
}

await writeFile(
  join(output, "THIRD_PARTY_NOTICES.txt"),
  [
    "Tesseract.js 6.0.1 and Tesseract.js Core 6.0.0",
    "Copyright their respective contributors; licensed under Apache License 2.0.",
    "https://github.com/naptha/tesseract.js/blob/master/LICENSE",
    "https://github.com/naptha/tesseract.js-core/blob/master/LICENSE",
    "",
    "Spanish traineddata (spa, 4.0.0_best_int), package @tesseract.js-data/spa 1.0.0.",
    "Package license: MIT. Model derived from the Tesseract OCR language data.",
    "https://github.com/naptha/tessdata",
    "",
  ].join("\n"),
);
