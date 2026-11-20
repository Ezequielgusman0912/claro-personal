const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "static", "registro", "app.js"), "utf8",
);

function setup(href = "https://cuentas.test/") {
  const events = {};
  const status = {};
  const links = ["/", "/#movimientos", "/?status=pending", "/cuentas/"].map((url, index) => {
    const classes = new Set(index === 0 ? ["active"] : []);
    const attributes = new Map();
    return {
      href: `https://cuentas.test${url}`,
      classList: {
        contains: (name) => classes.has(name),
        toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
      },
      setAttribute: (name, value) => attributes.set(name, value),
      removeAttribute: (name) => attributes.delete(name),
      hasAttribute: (name) => attributes.has(name),
      attributes,
    };
  });
  const navigation = {
    querySelectorAll: () => links,
    addEventListener: (name, handler) => { events[name] = handler; },
  };
  const window = {
    location: { href },
    addEventListener: (name, handler) => { events[name] = handler; },
  };
  vm.runInNewContext(source, {
    URL, window,
    document: {
      querySelector: (selector) => selector === ".sidebar nav"
        ? navigation : selector === "[data-navigation-status]" ? status : null,
    },
  });
  function click(index, extra = {}) {
    const event = {
      target: { closest: () => links[index] }, button: 0,
      preventDefault() { this.defaultPrevented = true; },
      ...extra,
    };
    events.click(event);
    return event;
  }
  return { links, window, events, status, click };
}

test("switches selection immediately and shows loading only on the target", () => {
  const app = setup();
  app.click(2);
  assert.equal(app.links[0].classList.contains("active"), false);
  assert.equal(app.links[2].classList.contains("active"), true);
  assert.equal(app.links[2].classList.contains("is-loading"), true);
  assert.equal(app.links[2].attributes.get("aria-busy"), "true");
  assert.match(app.status.textContent, /Cargando/);
  app.click(3);
  assert.equal(app.links[2].classList.contains("active"), false);
  assert.equal(app.links[2].classList.contains("is-loading"), false);
  assert.equal(app.links[3].classList.contains("is-loading"), true);
});

test("hash navigation selects Movimientos without a loading spinner", () => {
  const app = setup();
  app.click(1);
  assert.equal(app.links[1].classList.contains("active"), true);
  assert.equal(app.links[1].classList.contains("is-loading"), false);
  app.window.location.href = app.links[1].href;
  app.events.hashchange();
  assert.equal(app.links[1].attributes.get("aria-current"), "location");
  assert.equal(app.links[0].classList.contains("active"), false);
});

test("back navigation clears loading and restores the current section", () => {
  const app = setup();
  app.click(3);
  app.events.pageshow();
  assert.equal(app.links[0].classList.contains("active"), true);
  assert.equal(app.links[3].classList.contains("is-loading"), false);
  assert.equal(app.status.textContent, "");
});

test("modified clicks do not change selection or indicate page loading", () => {
  for (const extra of [{ ctrlKey: true }, { metaKey: true }, { button: 1 }]) {
    const app = setup();
    app.click(3, extra);
    assert.equal(app.links[0].classList.contains("active"), true);
    assert.equal(app.links[3].classList.contains("is-loading"), false);
  }
});

test("clicking the current section avoids an unnecessary reload", () => {
  const app = setup();
  assert.equal(app.click(0).defaultPrevented, true);
  assert.equal(app.links[0].classList.contains("is-loading"), false);
});
