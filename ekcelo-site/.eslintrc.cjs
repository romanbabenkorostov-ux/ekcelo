/**
 * ESLint конфиг — ESLint-границы между слоями (по SPEC_frontend §P0.1):
 * ui/* не должен импортировать adapters/*; core/* не зависит ни от чего.
 */
module.exports = {
  root: true,
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: 2022, sourceType: "module" },
  plugins: ["@typescript-eslint"],
  extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended"],
  rules: {
    "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    // Архитектурный guard: ui НЕ знает про adapters.
    "no-restricted-imports": [
      "error",
      {
        patterns: [
          {
            group: ["@adapters/*", "../adapters/*"],
            message: "ui/* не должен импортировать adapters/* (SPEC_frontend §P0.1)",
          },
        ],
      },
    ],
  },
  overrides: [
    {
      // В main.ts оркестрация — допустим импорт обоих слоёв.
      files: ["src/main.ts"],
      rules: { "no-restricted-imports": "off" },
    },
    {
      // В adapters/ нет ограничений на impl детали.
      files: ["src/adapters/**", "tests/**"],
      rules: { "no-restricted-imports": "off" },
    },
  ],
  ignorePatterns: ["dist", "node_modules"],
};
