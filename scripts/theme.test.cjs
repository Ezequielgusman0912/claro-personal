const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "static", "registro", "theme.js"), "utf8",
);

function setup(saved = null, dark = false, blocked = false) {
  const events = {};
  const dataset = {};
  const status = {};
  const selector = { addEventListener: (name, handler) => { events[name] = handler; } };
  const system = {
    matches: dark,
    addEventListener: (name, handler) => { events.system = handler; },
  };
  const storage = new Map([["cuentas-claras-theme", saved]]);
  const warnings = [];
  vm.runInNewContext(source, {
    document: {
      documentElement: { dataset },
      addEventListener: (name, handler) => { events[name] = handler; },
      querySelector: (query) => query === "[data-theme-select]" ? selector : status,
    },
    window: {
      matchMedia: () => system,
      localStorage: {
        getItem: (key) => {
          if (blocked) throw new Error("Storage blocked");
          return storage.get(key);
        },
        setItem: (key, value) => {
          if (blocked) throw new Error("Storage blocked");
          storage.set(key, value);
        },
      },
      addEventListener: (name, handler) => { events[name] = handler; },
    },
    console: { warn: (...args) => warnings.push(args) },
  });
  events.DOMContentLoaded();
  return { events, dataset, selector, system, storage, status, warnings };
}

test("uses system theme by default and follows system changes", () => {
  const app = setup(null, true);
  assert.equal(app.dataset.theme, "dark");
  assert.equal(app.selector.value, "system");
  app.system.matches = false;
  app.events.system();
  assert.equal(app.dataset.theme, "light");
});

test("saved selection applies before rendering and overrides system", () => {
  const app = setup("light", true);
  assert.equal(app.dataset.theme, "light");
  app.selector.value = "dark";
  app.events.change();
  assert.equal(app.dataset.theme, "dark");
  assert.equal(app.storage.get("cuentas-claras-theme"), "dark");
  app.system.matches = false;
  app.events.system();
  assert.equal(app.dataset.theme, "dark");
  app.selector.value = "system";
  app.events.change();
  assert.equal(app.dataset.theme, "light");
});

test("invalid stored values use system and other tabs synchronize", () => {
  const app = setup("invalid", true);
  assert.equal(app.dataset.theme, "dark");
  app.events.storage({ key: "cuentas-claras-theme", newValue: "light" });
  assert.equal(app.selector.value, "light");
  assert.equal(app.dataset.theme, "light");
  app.events.storage({ key: null, newValue: null });
  assert.equal(app.selector.value, "system");
});

test("blocked storage still allows theme changes and reports the failure", () => {
  const app = setup(null, false, true);
  app.selector.value = "dark";
  app.events.change();
  assert.equal(app.dataset.theme, "dark");
  assert.match(app.status.textContent, /no se pudo guardar/);
  assert.equal(app.warnings.length, 2);
});
