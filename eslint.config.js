const js = require("@eslint/js");
const globals = require("globals");

module.exports = [
  js.configs.recommended,
  {
    files: ["frontend/*.js"],
    languageOptions: {
      sourceType: "script",
      // app.js and flow.js are classic scripts sharing one global scope.
      globals: { ...globals.browser, module: "readonly", escapeHtml: "readonly", showToast: "readonly" },
    },
    rules: { "no-redeclare": "off", "no-unused-vars": ["error", { varsIgnorePattern: "^(escapeHtml|showToast)$" }] },
  },
  { files: ["tests/js/**", "eslint.config.js"], languageOptions: { sourceType: "commonjs", globals: globals.node } },
];
