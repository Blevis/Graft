# Graft logo

The mark is a twig cut for a **cleft graft**. The older wood (the stock) is cut into a V, and the new shoot (the scion)
is wedged into it. The join is a chevron of negative space, so you see the moment two pieces become one plant. One leaf
shows the shoot has taken hold. The stock is slightly heavier than the scion (old wood, new wood).
Concept exploration: `docs/brand-concepts.png`.

## Files (`frontend/public/orchid/`)

| File | Use |
|---|---|
| `graft.svg` | 40×40 app tile (rx 12, gradient #7954E8 → #3978F6, white twig). Sidebar, login, site header. |
| `graft-mark.svg` | The bare twig in `currentColor` (32×32 canvas). Use it inline wherever the mark appears without the tile. |
| `graft-favicon.svg` | 16×16 cut for browser tabs. It has heavier wood, a wider union gap and a bigger leaf. Use it below 24 px. |
| `graft-lockup-dark.svg` | Tile 40 + 12 gap + white "Graft" at 35 px. For the dark sidebar `#160E2E`. |
| `graft-lockup-light.svg` | Tile 32 + 10 gap + ink `#211B35` "Graft" at 26 px. For the light header `#F6F5FA` and white cards. |

The wordmark is Plus Jakarta Sans ExtraBold (800) with kerning and the same tracking as `.ow-brand` / `.ow-site-brand`.
It is converted to outlines, so it doesn't need the font. Plus Jakarta Sans is under the SIL Open Font License, which
allows logo use.

## Clear space
Leave at least **¼ of the tile's height** clear on every side: 10 px around a 40 px tile, 8 px around 32 px. For the
bare mark, use the leaf's length. In a lockup, keep the gap between tile and wordmark at 0.3× the tile height, as
built.

## Minimum size
- Tile: 24 px (`graft.svg`). Below that, use `graft-favicon.svg` (built for 16 px).
- Bare mark: 16 px.
- Lockup: 24 px tall. Below that, use the tile alone.

## Colour variants
- **Primary:** white twig on the Orchid gradient tile.
- **Flat tile:** a white twig on solid `#5831BC` when gradients aren't possible (print, embroidery, single-ink).
- **One colour:** `graft-mark.svg` in white on dark (`#160E2E`, photos), in ink `#211B35` on light, or in `#5831BC`
  on white or `#F6F5FA`.
- The union gap and the leaf are real holes in the shape. The mark has no white fills, so it works on any background.

## Don't
- Don't close, fill or shrink the chevron gap. It carries the whole idea.
- Don't rotate the twig off 45°, mirror it, or add more leaves, roots, a pot or a full tree.
- Don't recolour the leaf separately, or add outlines, shadows, glows or gradients to the twig itself.
- Don't use `graft.svg` or `graft-mark.svg` below the minimum sizes. Switch to the favicon cut.
- Don't retype the wordmark in another font or weight, or change the tile-to-wordmark ratio.
- Don't put the gradient tile on a busy photo. Use the one-colour white mark instead.

The source geometry was generated in Python, so it can be re-built. The twig is two straight-sided pieces at exactly 45°
(the stock with round foot and V-notch, and the scion with wedge foot and round tip) plus one leaf made of two
quadratic curves. The cut runs at 45° inside a ~1.4-unit gap on the 40-unit grid. Trademark clearance has not been
checked. Run a search before registering the mark.
