// Bringing the chosen square into view. SPEC 11.32.
//
// Choosing a place and not being shown it is the oldest fault a map can
// have. It happens here in three ordinary ways: a town is searched for while
// the map is somewhere else; the square is at the very edge of the canvas,
// where its ring is half drawn and a reader has to guess; or the bottom
// sheet opens on a phone, which makes the map shorter, and the square that
// was in the middle of it is now below the bottom of it.
//
// So after a square is chosen the map moves, by as little as will do, until
// the square is comfortably inside the part of the map a reader can actually
// see. The zoom never changes: the reader chose it, or the fit did, and a
// map that jumps to a different scale every time a town is searched for is a
// worse map than one that pans.
//
// No imports, so `node` can load this file and a test can drive it with the
// shapes a phone and a desktop really produce (SPEC 11.24).

/** How close to the edge is too close, in pixels. */
export const EDGE = 40;

/**
 * How far inside the edge a square is put when it has to be moved.
 *
 * Bigger than EDGE on purpose. If a square a pixel outside the comfortable
 * box were moved to exactly the edge of it, the map would slide by one
 * pixel: an animation a reader cannot see the point of. Moving it to twice
 * the margin makes every move worth making, and still never moves a square
 * that was already comfortable.
 */
export const REST = 2 * EDGE;

/** The ease, in milliseconds. Long enough to follow, short enough to wait. */
export const EASE_MS = 600;

/**
 * The part of the map a reader can actually see, in canvas pixels.
 *
 * The canvas is not always all on the screen: the page can be scrolled, and
 * on a phone the bottom sheet takes the lower half of the window, so the
 * bottom of the map can be under it or past the end of the window. This is
 * the canvas box clipped to the window, moved into the canvas's own
 * coordinates, which is the box everything below is measured against.
 */
export function visibleBox(canvas, window_) {
  if (!canvas || !window_) return null;
  const left = Math.max(0, -canvas.left);
  const top = Math.max(0, -canvas.top);
  const right = Math.min(canvas.width, window_.width - canvas.left);
  const bottom = Math.min(canvas.height, window_.height - canvas.top);
  return { left, top, right, bottom };
}

/**
 * One axis: how far to pan so `at` is comfortable between `low` and `high`.
 *
 * Positive means the map pans that way, which moves the square the other
 * way, which is what MapLibre's `panBy` does with the number it is given.
 */
function along(at, low, high) {
  const first = low + EDGE;
  const last = high - EDGE;
  if (last <= first) {
    // Nothing like enough room for a margin: put it in the middle of what
    // there is, which on a 100 pixel strip of map is the best there is.
    return at - (low + high) / 2;
  }
  if (at >= first && at <= last) return 0;
  const middle = (first + last) / 2;
  const target = at < first
    ? Math.min(low + REST, middle)
    : Math.max(high - REST, middle);
  return at - target;
}

/**
 * How far to pan the map so the square is in view, or null to stay put.
 *
 * `at` is where the square's centre is on the canvas, in canvas pixels, and
 * `box` is what `visibleBox` gave. The answer is `[x, y]` for `panBy`.
 */
export function nudge(at, box) {
  if (!at || !box) return null;
  if (!Number.isFinite(at.x) || !Number.isFinite(at.y)) return null;
  for (const side of ['left', 'top', 'right', 'bottom']) {
    if (!Number.isFinite(box[side])) return null;
  }
  const x = along(at.x, box.left, box.right);
  const y = along(at.y, box.top, box.bottom);
  if (x === 0 && y === 0) return null;
  return [x, y];
}
