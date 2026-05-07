# Dashboard UI Notes

## Current concept
Light brutalism dashboard for the job/news tracker.

## Visual direction
- Base background: white, warm off-white, or light gray.
- Surface: paper-like cards and panels.
- Shape: square corners, no soft SaaS rounding.
- Borders: visible but softened dark gray, not pure black.
- Shadows: hard offset brutalist shadows, but low-opacity so they do not feel too heavy.
- Typography: bold, compact, utilitarian.
- Accent colors: limited punchy colors such as orange, blue, yellow, green, red.

## Current CSS tokens
Defined in `src/App.css`:

```css
--ink: #111111;
--line: rgba(17, 17, 17, 0.58);
--paper: #fbfbf6;
--paper-2: #eeeee6;
--paper-3: #e3e3d8;
--accent: #ff5a1f;
--accent-2: #215cff;
--border: 2px solid var(--line);
--shadow: 5px 5px 0 rgba(17, 17, 17, 0.42);
--shadow-sm: 3px 3px 0 rgba(17, 17, 17, 0.38);
```

## Keep
- Brutalist layout language.
- Light background.
- Strong but not harsh borders.
- Offset shadow interaction on cards/buttons.
- High readability.

## Avoid
- Dark neon dashboard style.
- Glassmorphism / blur panels.
- Fully black heavy outlines everywhere.
- Rounded SaaS-style cards.
- Too many gradients.
- Excessive visual noise.

## Change workflow
For future UI changes:

1. Preserve this visual direction unless explicitly asked otherwise.
2. Prefer token changes in `src/App.css` before changing many selectors.
3. For broad visual changes, update this file with the new direction.
4. Run `npm run build` after meaningful CSS/React changes.
