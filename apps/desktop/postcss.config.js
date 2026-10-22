import tailwindcss from "@tailwindcss/postcss";

// Keep existing component classes visually stable during the compiler upgrade.
// Transform only known generated utility shapes, never application CSS.
const v3UtilityCompatibility = {
  postcssPlugin: "panelflow-tailwind-v3-compatibility",
  OnceExit(root) {
    root.walkRules((rule) => {
      const siblingUtility = /^:where\((\.[^\s]+) > :not\(:last-child\)\)$/.exec(rule.selector);
      if (siblingUtility) {
        const className = siblingUtility[1];
        const space = /(?:^|:)space-([xy])-/.exec(className.slice(1));
        const divide = /(?:^|:)divide-/.test(className.slice(1));
        if (space || divide) {
          rule.selector = `${className} > :not([hidden]) ~ :not([hidden])`;
          const properties = space
            ? space[1] === "y"
              ? { "margin-block-start": "margin-bottom", "margin-block-end": "margin-top" }
              : { "margin-inline-start": "margin-right", "margin-inline-end": "margin-left" }
            : {
                "border-top-width": "border-bottom-width",
                "border-bottom-width": "border-top-width",
                "border-inline-start-width": "border-right-width",
                "border-inline-end-width": "border-left-width",
              };
          rule.walkDecls((decl) => {
            if (properties[decl.prop]) decl.prop = properties[decl.prop];
          });
        }
      }
      if (rule.selector.includes(String.raw`\[\&_button\]\:focus-visible\:`) && rule.selector.endsWith(" button:focus-visible")) {
        rule.selector = rule.selector.replace(/ button:focus-visible$/, ":focus-visible button");
      }
      if (/(?:^\.|\\:)outline-none(?=[:\s]|$)/.test(rule.selector)) {
        rule.walkDecls((decl) => {
          if (decl.prop === "--tw-outline-style" || (decl.prop === "outline-style" && decl.value === "none")) decl.remove();
        });
      }
      if (/(?:^\.|\\:)bg-gradient-to-/.test(rule.selector)) {
        rule.walkDecls("--tw-gradient-position", (decl) => {
          decl.value = decl.value.replace(/ in oklab$/, "");
        });
      }
    });
  },
};

export default {
  // Vite minifies after this pass; keep generated selectors intact until then.
  plugins: [tailwindcss({ optimize: false }), v3UtilityCompatibility],
};
