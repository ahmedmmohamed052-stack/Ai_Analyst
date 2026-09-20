/*
 * i18n.js — tiny shared translation engine for AI Analyst (no build step).
 *
 * Used by both index.html and how-it-works.html. Language is stored in
 * localStorage, so switching on one page carries over to the other.
 *
 *   Static text     <span data-i18n="key">English default</span>
 *                   data-i18n-html / -placeholder / -title / -aria-label
 *   Dynamic text    I18N.t("key", { name: value })
 *   Backend errors  I18N.tError(message)   (see i18n-app.js -> addErrors)
 *   Toggle          <div data-lang-toggle></div>   -> sliding EN | عربي switch
 *   React to change window.addEventListener("langchange", e => e.detail.lang)
 *
 * Arabic switches the whole document to dir="rtl" and lang="ar".
 */
(function () {
  "use strict";

  var STORE_KEY = "ai_analyst_lang";
  var SUPPORTED = ["en", "ar"];
  var dicts = { en: {}, ar: {} };
  var errorRules = [];
  var current = "en";

  // ── language detection ─────────────────────────────────────────────────
  function detect() {
    try {
      var saved = localStorage.getItem(STORE_KEY);
      if (SUPPORTED.indexOf(saved) !== -1) return saved;
    } catch (e) { /* storage blocked — fall through */ }
    var nav = String(navigator.language || "en").toLowerCase();
    return nav.indexOf("ar") === 0 ? "ar" : "en";
  }

  // ── dictionary access ──────────────────────────────────────────────────
  function extend(lang, entries) {
    if (!dicts[lang]) dicts[lang] = {};
    for (var k in entries) {
      if (Object.prototype.hasOwnProperty.call(entries, k)) dicts[lang][k] = entries[k];
    }
  }

  function t(key, vars) {
    var s = dicts[current][key];
    if (s === undefined) s = dicts.en[key];
    if (s === undefined) return key;
    if (vars) {
      s = s.replace(/\{(\w+)\}/g, function (m, name) {
        return vars[name] !== undefined ? vars[name] : m;
      });
    }
    return s;
  }

  // Backend errors arrive as English strings in `detail`. Rules are
  // { en: "exact string" | RegExp, ar: "translation, $1 = first capture" }.
  function addErrors(rules) {
    errorRules = errorRules.concat(rules);
  }

  function tError(message) {
    if (current === "en" || !message) return message;
    var msg = String(message);
    for (var i = 0; i < errorRules.length; i++) {
      var rule = errorRules[i];
      if (typeof rule.en === "string") {
        if (msg === rule.en) return rule.ar;
      } else {
        var m = msg.match(rule.en);
        if (m) {
          return rule.ar.replace(/\$(\d)/g, function (x, n) {
            return m[+n] !== undefined ? tError(m[+n]) : "";
          });
        }
      }
    }
    return msg; // unknown message: show it untranslated rather than hide it
  }

  // ── DOM application ────────────────────────────────────────────────────
  function apply(root) {
    root = root || document;
    var nodes, i, el;

    nodes = root.querySelectorAll("[data-i18n]");
    for (i = 0; i < nodes.length; i++) {
      el = nodes[i];
      var txt = t(el.getAttribute("data-i18n"));
      if (el.tagName === "TITLE") document.title = txt; else el.textContent = txt;
    }
    nodes = root.querySelectorAll("[data-i18n-html]");
    for (i = 0; i < nodes.length; i++) {
      nodes[i].innerHTML = t(nodes[i].getAttribute("data-i18n-html"));
    }
    var attrs = ["placeholder", "title", "aria-label"];
    attrs.forEach(function (attr) {
      var sel = "[data-i18n-" + attr + "]";
      var list = root.querySelectorAll(sel);
      for (var j = 0; j < list.length; j++) {
        list[j].setAttribute(attr, t(list[j].getAttribute("data-i18n-" + attr)));
      }
    });
  }

  function applyDocument() {
    var de = document.documentElement;
    de.setAttribute("lang", current);
    de.setAttribute("dir", current === "ar" ? "rtl" : "ltr");
  }

  // ── sliding EN | عربي switch ───────────────────────────────────────────
  var STYLE = [
    ".lang-switch{position:relative;display:inline-flex;align-items:center;flex-shrink:0;",
    "width:88px;height:34px;padding:0;border-radius:999px;border:1px solid rgba(255,255,255,.16);",
    "background:rgba(0,0,0,.32);cursor:pointer;direction:ltr;overflow:hidden;",
    "color:#a29bc2;font:600 12.5px/1 'Space Grotesk','Tajawal',sans-serif;",
    "-webkit-tap-highlight-color:transparent;transition:border-color .2s ease}",
    ".lang-switch:hover{border-color:rgba(124,92,255,.7)}",
    ".lang-switch:focus-visible{outline:2px solid #38e0c8;outline-offset:2px}",
    ".lang-switch .lang-opt{flex:1;text-align:center;position:relative;z-index:2;",
    "user-select:none;transition:color .25s ease}",
    ".lang-switch .lang-ar{font-family:'Tajawal','Space Grotesk',sans-serif;font-size:13.5px;letter-spacing:0}",
    ".lang-switch .lang-knob{position:absolute;top:3px;left:3px;width:40px;height:26px;",
    "border-radius:999px;z-index:1;",
    "background:linear-gradient(135deg,#7c5cff 0%,#ff5cb3 55%,#38e0c8 100%);",
    "box-shadow:0 4px 14px rgba(124,92,255,.45);",
    "transition:transform .38s cubic-bezier(.34,1.56,.64,1)}",
    ".lang-switch[aria-checked='true'] .lang-knob{transform:translateX(40px)}",
    ".lang-switch[aria-checked='false'] .lang-en,.lang-switch[aria-checked='true'] .lang-ar{color:#0b0a14}",
    ".lang-float{position:absolute;top:18px;inset-inline-end:18px;z-index:5}",
    "@media (prefers-reduced-motion:reduce){.lang-switch .lang-knob{transition:none}}"
  ].join("");

  function injectStyle() {
    if (document.getElementById("i18n-toggle-style")) return;
    var s = document.createElement("style");
    s.id = "i18n-toggle-style";
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  function buildToggle() {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "lang-switch";
    btn.setAttribute("role", "switch");
    btn.setAttribute("aria-label", "Language / اللغة");
    btn.setAttribute("data-lang-switch", "");
    btn.innerHTML =
      '<span class="lang-knob"></span>' +
      '<span class="lang-opt lang-en">EN</span>' +
      '<span class="lang-opt lang-ar">عربي</span>';
    btn.addEventListener("click", function () {
      setLang(current === "ar" ? "en" : "ar");
    });
    return btn;
  }

  function syncToggles() {
    var sw = document.querySelectorAll("[data-lang-switch]");
    for (var i = 0; i < sw.length; i++) {
      sw[i].setAttribute("aria-checked", current === "ar" ? "true" : "false");
    }
  }

  function mountToggles() {
    injectStyle();
    var hosts = document.querySelectorAll("[data-lang-toggle]");
    for (var i = 0; i < hosts.length; i++) {
      if (!hosts[i].querySelector("[data-lang-switch]")) hosts[i].appendChild(buildToggle());
    }
    syncToggles();
  }

  // ── public API ─────────────────────────────────────────────────────────
  function setLang(lang, silent) {
    if (SUPPORTED.indexOf(lang) === -1) return;
    var changed = lang !== current;
    current = lang;
    try { localStorage.setItem(STORE_KEY, lang); } catch (e) { /* ignore */ }
    applyDocument();
    apply(document);
    syncToggles();
    if (changed && !silent) {
      window.dispatchEvent(new CustomEvent("langchange", { detail: { lang: lang } }));
    }
  }

  function formatDate(iso) {
    try {
      var d = new Date(iso);
      // Latin digits (ar-EG-u-nu-latn) keep numbers consistent with the rest of the UI.
      return d.toLocaleString(current === "ar" ? "ar-EG-u-nu-latn" : undefined);
    } catch (e) {
      return String(iso);
    }
  }

  current = detect();
  applyDocument(); // set lang/dir before first paint

  window.I18N = {
    extend: extend,
    addErrors: addErrors,
    t: t,
    tError: tError,
    apply: apply,
    setLang: setLang,
    formatDate: formatDate,
    lang: function () { return current; },
    isRTL: function () { return current === "ar"; }
  };

  function boot() {
    mountToggles();
    apply(document);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();