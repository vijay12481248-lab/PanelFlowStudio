# Desktop dependency-audit remediation

## Decision

Replace Tailwind 3.4.19 with pinned `tailwindcss@4.3.3` and `@tailwindcss/postcss@4.3.3`. Keep the existing PostCSS integration to limit build-system changes; Vite configuration and application components do not need to change. Remove the now-redundant direct Autoprefixer dependency. Preserve `jsdom@26.1.0` and existing uncommitted work. No audit filtering, dependency overrides, or `npm audit fix --force` is used.

The reproduced audit reported **7 findings: 5 high, 2 moderate**. Both chains originate in Tailwind 3:

- Tailwind → Chokidar/Micromatch/Fast-glob → Braces 3.0.3.
- Tailwind → PostCSS Nested → PostCSS Selector Parser 6.1.4.

The replacement lockfile removes these packages rather than hiding the paths. The final audit reports **0 vulnerabilities**.

## Primary references

- Braces advisory, affected through 3.0.3, no patched version listed: https://github.com/advisories/GHSA-vfj7-8cjw-p6xm
- Maintainer selector-parser advisory, fixed in 7.1.6; trusted ordinary build inputs are not the described request-path exposure: https://github.com/advisories/GHSA-rj75-hqrm-r3gf
- Official migration guide, dedicated integration packages and v4 breaking changes: https://tailwindcss.com/docs/upgrade-guide

## Compatibility boundaries

`src/index.css` explicitly scans the desktop HTML, desktop source, and shared `packages/ui/src` relative to the stylesheet, not the shell working directory. It explicitly loads the existing JavaScript configuration using `@config`.

`tailwind.config.js` preserves the installed v3 palette, shadow, drop-shadow, radius, and blur scales. The root stylesheet restores v3 border/ring/placeholder/cursor/dialog defaults, hover behavior, transparent forced-colors outlines, inset shadow, and deprecated flex utilities used by existing components.

A narrow PostCSS compatibility pass restores v3 hidden-sibling spacing/dividers, sRGB gradient direction, and the existing arbitrary descendant focus-variant ordering. Tailwind optimization is disabled only until this pass completes; Vite still minifies production CSS. Tests assert unrelated application rules are not rewritten. Review this pass against generated CSS when upgrading Tailwind again.

Application-wide defaults live in `@layer base`. This matters: an unlayered `font: inherit` overrides layered text-size/font-weight utilities in v4. A real Chromium differential fixture reproduced a button changing from 12px/600 to 16px/400 before the fix; after the fix, sampled typography, colors, radius, hidden-sibling spacing/dividers, and backdrop blur match the saved v3 baseline.

V4 requires modern browsers (Chrome 111+, Safari 16.4+, Firefox 128+). Validate the actual Tauri WebView runtime and live screens before release. The sampled CSS comparison is not a complete application-wide screenshot or installer acceptance test. Individual CSS transform properties and native cascade layers remain v4 framework behavior; future component styles must account for them.

## Executed gate snapshot

- `npm audit --json`: exit 0, zero vulnerabilities across all severities.
- `npm ls --all`: exit 0, no invalid dependency tree.
- Desktop frontend suite: **146 passed, 0 failed**, including 7 focused migration tests.
- Expanded desktop + package frontend suite: **149 passed, 1 failed** out of 150. The concurrent API-client image test retained a previous-session token; no API-client code was changed for this migration.
- An earlier full workspace build passed after the dependency upgrade. The latest `npm run build` is blocked by concurrent `packages/api-client/src/index.ts:184`, TS2339: `authenticatedRequest` does not exist on `PanelFlowApiClient`. Do not call the current full workspace gate green until its owner repairs it and reruns the command.
- The final Vite production pipeline itself passed (2,013 modules, generated CSS 122.80 kB); this was exercised through `node --input-type=module -e "import { build } from 'vite'; await build({ root: 'apps/desktop' });"` to verify the real CSS/configuration chain despite the unrelated TypeScript blocker.
- `git diff --check`: exit 0; Git reported LF-to-CRLF normalization notices.
- `graphify update .`: exit 0; existing extraction warnings report 18 files with zero nodes and 8 SQL files without `tree_sitter_sql`.

Actual logs and the saved v3/v4 browser fixture are under `C:/Users/Vijaya sekhar/AppData/Local/hermes/cache/scratch/panelflow-*`.

## Repeatable verification

```bash
npm audit --json
npm ls --all
npm run build
shopt -s globstar nullglob
npx --yes tsx --tsconfig apps/desktop/tsconfig.json --test apps/desktop/src/**/*.test.ts apps/desktop/src/**/*.test.tsx packages/*/src/**/*.test.ts
git diff --check
graphify update .
```

The focused `tailwindMigration.test.ts` suite compiles the actual configured stylesheet, verifies shared-UI scanning independently of desktop scanning, checks visual tokens and compatibility selectors/cascade, and rejects reintroduction of the removed vulnerable chains or manifest overrides.

Build-chain warnings unrelated to vulnerabilities must remain visible. This environment reported a Vite bundle larger than 500 kB and an install-policy warning that the `esbuild@0.25.12` postinstall script was blocked. Do not disable those policies or increase warning thresholds to conceal them.

Rollback must restore this migration's package/configuration/CSS changes together and re-install the corresponding lockfile; that reintroduces the original audit findings. Do not reset unrelated work in the shared checkout.
