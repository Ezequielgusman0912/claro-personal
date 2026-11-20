const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "static", "registro", "app.js"), "utf8",
);

function setup({ width = 1080, height = 2400, invalidImage = false } = {}) {
  const alerts = [];
  const revoked = [];
  const events = {};
  const fields = Object.fromEntries(
    ["amount", "date", "recipient", "operation_id", "currency", "account"]
      .map((key) => [`#id_${key}`, { value: "" }]),
  );
  const file = { name: "captura.png", type: "image/png", size: 1024 };
  const fileField = { files: [file], value: "captura.png", addEventListener() {} };
  const button = {};
  const label = {};
  const spinner = {};
  const status = {};
  const manual = {};
  const result = {};
  const elements = {
    "[data-upload-button]": button,
    "[data-upload-label]": label,
    "[data-upload-spinner]": spinner,
    "[data-manual-entry]": manual,
    'input[type="file"]': fileField,
    ".ocr-status": status,
    "[name=csrfmiddlewaretoken]": { value: "csrf" },
  };
  const upload = {
    dataset: {},
    action: "/extraer/",
    querySelector: (selector) => elements[selector],
    setAttribute() {},
    addEventListener: (event, handler) => { events[event] = handler; },
  };
  const drawing = [];
  const canvas = {
    getContext: () => ({
      fillRect: (...args) => drawing.push(["fill", ...args]),
      drawImage: (...args) => drawing.push(["draw", ...args]),
    }),
  };
  let recognized;
  let terminated = false;
  class BrowserImage {
    naturalWidth = width;
    naturalHeight = height;
    set src(value) {
      queueMicrotask(() => invalidImage ? this.onerror() : this.onload());
    }
  }
  vm.runInNewContext(source, {
    document: {
      querySelector: (selector) => {
        if (selector === ".upload-form[data-worker-url]") return upload;
        if (selector === "[data-ocr-result]") return result;
        if (selector === "#manual") return { scrollIntoView() {} };
        return fields[selector] || null;
      },
      createElement: (tag) => {
        assert.equal(tag, "canvas");
        return canvas;
      },
    },
    Image: BrowserImage,
    URL: {
      createObjectURL: () => "blob:local-receipt",
      revokeObjectURL: (url) => revoked.push(url),
    },
    createImageBitmap: async () => {
      throw new Error("The source image could not be decoded.");
    },
    window: {
      alert: (message) => alerts.push(message),
      Tesseract: {
        createWorker: async () => ({
          recognize: async (image) => {
            recognized = image;
            return { data: { text: "Importe $ 1234" } };
          },
          terminate: async () => { terminated = true; },
        }),
      },
    },
    fetch: async () => ({
      ok: true,
      json: async () => ({ data: { amount: "1234.00" } }),
    }),
    URLSearchParams,
    console: { error() {} },
  });
  return {
    submit: () => events.submit({ preventDefault() {} }),
    alerts, revoked, upload, canvas, drawing, fields, fileField, button, spinner,
    get recognized() { return recognized; },
    get terminated() { return terminated; },
  };
}

test("loads a screenshot even when createImageBitmap cannot decode it", async () => {
  const app = setup();
  await app.submit();
  assert.deepEqual(app.alerts, []);
  assert.equal(app.recognized, app.canvas);
  assert.equal(app.canvas.width, 1080);
  assert.equal(app.canvas.height, 2400);
  assert.equal(app.fields["#id_amount"].value, "1234.00");
  assert.equal(app.upload.dataset.ocrComplete, "true");
  assert.equal(app.button.disabled, true);
  assert.equal(app.spinner.hidden, true);
  assert.equal(app.terminated, true);
  assert.deepEqual(app.revoked, ["blob:local-receipt"]);
});

test("limits the OCR image size without changing its aspect ratio", async () => {
  const app = setup({ width: 2000, height: 8000 });
  await app.submit();
  assert.deepEqual(app.alerts, []);
  assert.equal(app.canvas.width, 800);
  assert.equal(app.canvas.height, 3200);
  assert.equal(app.drawing[0][0], "fill");
  assert.equal(app.drawing[1][0], "draw");
});

test("an undecodable file shows a Spanish error and allows retry", async () => {
  const app = setup({ invalidImage: true });
  await app.submit();
  assert.match(app.alerts[0], /No pudimos abrir esta imagen/);
  assert.equal(app.fileField.value, "");
  assert.equal(app.button.disabled, false);
  assert.equal(app.spinner.hidden, true);
  assert.equal(app.recognized, undefined);
  assert.deepEqual(app.revoked, ["blob:local-receipt"]);
});

test("rejects images above 20 megapixels before starting OCR", async () => {
  const app = setup({ width: 5000, height: 5000 });
  await app.submit();
  assert.match(app.alerts[0], /20 megapíxeles/);
  assert.equal(app.recognized, undefined);
  assert.equal(app.button.disabled, false);
  assert.deepEqual(app.revoked, ["blob:local-receipt"]);
});
