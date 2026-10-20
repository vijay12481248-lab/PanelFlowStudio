# PanelFlow Studio Design System
# Generated and enhanced with Google Stitch MCP

## Design Tokens

### Color Palette

#### Primary Colors
```css
--pf-primary-50: #eef2ff
--pf-primary-100: #e0e7ff
--pf-primary-500: #6366f1  /* Indigo - Primary brand color */
--pf-primary-600: #4f46e5
--pf-primary-900: #312e81

--pf-accent-50: #faf5ff
--pf-accent-100: #f3e8ff
--pf-accent-500: #8b5cf6  /* Violet - Accent */
--pf-accent-600: #7c3aed
--pf-accent-900: #4c1d95
```

#### Dark Theme Base
```css
--pf-bg-primary: #080b12        /* Deep space black */
--pf-bg-secondary: #0c0e17      /* Card background */
--pf-bg-tertiary: #111422       /* Elevated surfaces */
--pf-bg-quaternary: #151928     /* Raised elements */

--pf-border-primary: #1e2538     /* Primary borders */
--pf-border-secondary: #181c2b  /* Secondary borders */
--pf-border-accent: #6366f1/30  /* Accent borders */

--pf-text-primary: #fafafa       /* Primary text */
--pf-text-secondary: #a1a1aa    /* Secondary text */
--pf-text-tertiary: #71717a     /* Muted text */
--pf-text-accent: #6366f1       /* Accent text */
```

#### Status Colors
```css
/* Success */
--pf-success-50: #ecfdf5
--pf-success-400: #34d399
--pf-success-500: #10b981

/* Warning */
--pf-warning-50: #fffbeb
--pf-warning-400: #fbbf24
--pf-warning-500: #f59e0b

/* Error */
--pf-error-50: #fef2f2
--pf-error-400: #f87171
--pf-error-500: #ef4444

/* Info */
--pf-info-50: #eff6ff
--pf-info-400: #60a5fa
--pf-info-500: #3b82f6
```

### Typography

#### Font Families
```css
--pf-font-display: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif
--pf-font-body: 'Inter', system-ui, -apple-system, sans-serif
--pf-font-mono: 'JetBrains Mono', 'Fira Code', monospace
```

#### Type Scale
```css
/* Headings */
--pf-text-4xl: 2rem   /* 32px */
--pf-text-3xl: 1.875rem /* 30px */
--pf-text-2xl: 1.5rem /* 24px */
--pf-text-xl: 1.25rem /* 20px */

/* Body */
--pf-text-lg: 1.125rem /* 18px */
--pf-text-base: 1rem   /* 16px */
--pf-text-sm: 0.875rem /* 14px */
--pf-text-xs: 0.75rem  /* 12px */
--pf-text-2xs: 0.625rem /* 10px */
```

#### Font Weights
```css
--pf-font-light: 300
--pf-font-normal: 400
--pf-font-medium: 500
--pf-font-semibold: 600
--pf-font-bold: 700
--pf-font-black: 900
```

### Spacing Scale

```css
--pf-space-1: 0.25rem   /* 4px */
--pf-space-2: 0.5rem    /* 8px */
--pf-space-3: 0.75rem   /* 12px */
--pf-space-4: 1rem      /* 16px */
--pf-space-5: 1.25rem   /* 20px */
--pf-space-6: 1.5rem    /* 24px */
--pf-space-8: 2rem      /* 32px */
--pf-space-10: 2.5rem   /* 40px */
--pf-space-12: 3rem     /* 48px */
--pf-space-16: 4rem     /* 64px */
```

### Border Radius

```css
--pf-radius-sm: 0.375rem   /* 6px */
--pf-radius-md: 0.5rem     /* 8px */
--pf-radius-lg: 0.75rem    /* 12px */
--pf-radius-xl: 1rem       /* 16px */
--pf-radius-2xl: 1.5rem    /* 24px */
--pf-radius-full: 9999px
```

### Shadows

```css
--pf-shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05)
--pf-shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1)
--pf-shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1)
--pf-shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1)
--pf-shadow-2xl: 0 25px 50px -12px rgb(0 0 0 / 0.25)
--pf-shadow-glow: 0 0 40px rgb(99 102 241 / 0.3)
```

### Animation

```css
--pf-duration-fast: 150ms
--pf-duration-normal: 250ms
--pf-duration-slow: 350ms

--pf-ease-in: cubic-bezier(0.4, 0, 1, 1)
--pf-ease-out: cubic-bezier(0, 0, 0.2, 1)
--pf-ease-in-out: cubic-bezier(0.4, 0, 0.2, 1)
```

## Component Specifications

### System Cards

**Enhanced System Overview Card**

- Background: Glassmorphism with backdrop-blur-xl
- Border: 1px solid rgba(255,255,255,0.1)
- Padding: 20px
- Border Radius: 16px (2xl)
- Hover: Scale 1.02, enhanced shadow

**Visual Elements:**
- Icon container: 48x48px, rounded-xl
- Gradient background matching status
- Micro-interactions on hover
- Progress indicator

### Project Cards

**Enhanced Project Card**

- Aspect Ratio: 16:10
- Cover image with gradient overlay
- Progress ring indicator
- Quick actions on hover
- Metadata display

### Navigation

**App Navigation Rail**
- Width: 68px
- Background: Glass blur
- Icons: 24x24px
- Active state: Indigo glow
- Tooltip on hover (desktop)

### Buttons

**Primary Button**
- Background: Linear gradient indigo-600 → indigo-700
- Padding: 12px 24px
- Border radius: 12px
- Hover: Scale 1.02, enhanced shadow
- Active: Scale 0.98

**Secondary Button**
- Background: Zinc-800
- Border: 1px solid zinc-700
- Hover: Background zinc-700

### Inputs

**Text Input**
- Background: Zinc-950
- Border: 1px solid zinc-700
- Focus: Border indigo-500, ring indigo-500/20
- Padding: 12px 16px
- Border radius: 12px

## Glassmorphism Effects

```css
.glass {
  background: rgba(12, 14, 23, 0.6);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.glass-strong {
  background: rgba(12, 14, 23, 0.8);
  backdrop-filter: blur(32px);
  -webkit-backdrop-filter: blur(32px);
  border: 1px solid rgba(255, 255, 255, 0.15);
}
```

## Responsive Breakpoints

```css
--pf-breakpoint-sm: 640px
--pf-breakpoint-md: 768px
--pf-breakpoint-lg: 1024px
--pf-breakpoint-xl: 1280px
--pf-breakpoint-2xl: 1536px
```

## Accessibility

- Minimum contrast ratio: 4.5:1 for text
- Focus indicators: Visible focus rings
- Keyboard navigation: All interactive elements accessible
- Screen reader support: Proper ARIA labels
- Reduced motion: Respects prefers-reduced-motion

## Stitch MCP Integration

This design system is designed to be generated and maintained using Google Stitch MCP:

1. **Design System Creation**
   ```
   mcp_stitch_create_design_system(
     project_name: "PanelFlow Studio",
     description: "Professional AI manga production suite",
     colors: [...],
     typography: [...],
     components: [...]
   )
   ```

2. **Component Generation**
   ```
   mcp_stitch_generate_components(
     component_type: "system-card",
     variants: ["glass", "solid", "minimal"]
   )
   ```

3. **Screen Generation**
   ```
   mcp_stitch_create_screen(
     screen_type: "dashboard",
     layout: "three-column",
     components: [...]
   )
   ```

## Implementation Notes

- Tailwind CSS custom configuration required
- CSS variables for theme switching
- Component library in packages/ui
- Storybook for component documentation
- Dark mode only (no light mode variant)

## Migration Path

1. Audit existing components
2. Create design tokens
3. Update existing components incrementally
4. Migrate to glassmorphism effects
5. Enhance interactions and micro-animations
6. Add responsive improvements
