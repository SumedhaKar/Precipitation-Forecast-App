// The pictures, written out as rectangles and lines. SPEC 11.34.
//
// No chart library. Twelve small plots of five points and two grids of 109
// rectangles do not need 40 KB of one, and a library would put a layer
// between the numbers in the file and the shapes on the screen that nothing
// could test through. Every number here is placed by arithmetic a reader can
// follow, and every plot carries its numbers in a table underneath or in the
// shape's own title, because a picture is not readable (SPEC 11.22).

const COLOUR = {
  above: '#1b5e20',
  unsure: '#7a4100',
  zero: '#1f2933',
  axis: '#7b8794',
  ink: '#52606d',
};

/** Where a value sits in a box, given the range the box covers. */
export function place(value, low, high, size) {
  if (high === low) return size / 2;
  return size - ((value - low) / (high - low)) * size;
}

/**
 * Skill against lead day, with the range each point carries.
 *
 * The zero line is always drawn and always labelled, because "better than
 * the usual rain for this place and month" is exactly the question of which
 * side of it the range falls on.
 */
export function SkillPlot({ title, series, foot = true, width = 240,
  height = 150 }) {
  const pad = { left: 38, right: 8, top: 10, bottom: 22 };
  const box = {
    w: width - pad.left - pad.right,
    h: height - pad.top - pad.bottom,
  };
  const values = series.flatMap(
    (point) => [point.lo, point.hi, point.bss]).filter(
    (value) => value !== null && value !== undefined);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const span = high - low || 1;
  const y = (value) => pad.top + place(value, low - span * 0.08,
    high + span * 0.08, box.h);
  const x = (lead) => pad.left + (box.w / series.length) * (lead - 0.5);
  return (
    <figure className="plot">
      <figcaption>{title}</figcaption>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${title}. ${series.map(
          (point) => `Day ${point.lead}, ${point.bss === null ? 'no number'
            : point.bss.toFixed(2)}, from ${Number(point.lo).toFixed(2)} to `
            + `${Number(point.hi).toFixed(2)}`).join('. ')}.`}
      >
        <line
          x1={pad.left} x2={width - pad.right} y1={y(0)} y2={y(0)}
          stroke={COLOUR.zero} strokeWidth="1" strokeDasharray="3 3"
        />
        <text x="2" y={y(0) + 3} fill={COLOUR.ink} fontSize="9">0</text>
        <text x="2" y={y(high) + 3} fill={COLOUR.ink} fontSize="9">
          {high.toFixed(2)}
        </text>
        {low < 0 ? (
          <text x="2" y={y(low) + 3} fill={COLOUR.ink} fontSize="9">
            {low.toFixed(2)}
          </text>
        ) : null}
        {series.map((point) => {
          if (point.bss === null || point.bss === undefined) return null;
          const colour = point.above ? COLOUR.above : COLOUR.unsure;
          return (
            <g key={point.lead}>
              <line
                x1={x(point.lead)} x2={x(point.lead)}
                y1={y(point.lo)} y2={y(point.hi)}
                stroke={colour} strokeWidth="2"
              />
              <circle
                cx={x(point.lead)} cy={y(point.bss)} r="3" fill={colour}
              />
              <text
                x={x(point.lead)} y={height - 6} fontSize="9"
                textAnchor="middle" fill={COLOUR.ink}
              >
                {point.lead}
              </text>
            </g>
          );
        })}
      </svg>
      {foot ? (
        <p className="plotfoot">
          Day 1 to 5 across. The bar is the range and the dot is the score;
          dark green where the whole range is above 0.
        </p>
      ) : null}
    </figure>
  );
}

// The 2-degree maps. One rectangle per cell, laid out by latitude and
// longitude so the shape of India appears without any geometry: the cells
// are 2 degrees across and the box is SPEC 1.4's.
const BOX = { south: 6, north: 38, west: 68, east: 98 };
const CELL = 2;

// The same blue-green family as the map's (SPEC 11.17), and one colour that
// is not in it at all for a cell below 0. Stretching one ramp from the worst
// cell to the best would paint "a little better than the usual rain" and "a
// lot better" the same dark blue, and it would hide the sign, which on a
// skill map is the whole question.
export const BELOW = '#d8b08c';

export function ramp(value, high) {
  if (value === null || value === undefined) return '#ffffff';
  if (value < 0) return BELOW;
  const steps = ['#edf8b1', '#c7e9b4', '#7fcdbb', '#41b6c4', '#1d91c0',
    '#225ea8', '#0c2c84'];
  if (!(high > 0)) return steps[0];
  return steps[Math.min(steps.length - 1,
    Math.floor((value / high) * steps.length))];
}

export function CellMap({ title, cells, pick, high, least, width = 300 }) {
  const across = (BOX.east - BOX.west) / CELL;
  const down = (BOX.north - BOX.south) / CELL;
  const size = width / across;
  const height = size * down;
  return (
    <figure className="plot">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        {cells.map((cell) => {
          const value = pick(cell);
          const x = ((cell.lon - BOX.west) / CELL) * size;
          const y = ((BOX.north - CELL - cell.lat) / CELL) * size;
          return (
            <rect
              key={`${cell.lat}_${cell.lon}`}
              x={x} y={y} width={size - 0.5} height={size - 0.5}
              fill={ramp(value, high)}
              stroke={cell.enough ? '#dbe1e8' : '#7b8794'}
              strokeWidth={0.5}
              strokeDasharray={cell.enough ? undefined : '1.5 1.5'}
            >
              <title>
                {`${cell.lat} N ${cell.lon} E, ${cell.squares} squares: `
                  + `${value === null ? 'no number'
                    : Number(value).toFixed(3)}`}
              </title>
            </rect>
          );
        })}
      </svg>
      <p className="plotfoot">
        One rectangle per 2 degree cell, 0 to {high.toFixed(2)}, lighter is
        lower; a tan cell is below 0. A dashed edge is a cell with fewer than
        {' '}{least} forecast squares in it, which is drawn and not read from.
      </p>
    </figure>
  );
}
