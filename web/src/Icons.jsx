// The five icons this site draws. SPEC 11.39.
//
// Inline SVG, written out here: no icon library, no webfont, no emoji. An
// icon library would be a download for five shapes; emoji are drawn by the
// reader's own system and a rain cloud is a different picture on every
// platform, which is not something a site's own mark may be.
//
// Every one of them is 24 by 24 on a 24 unit grid, takes its colour from
// `currentColor`, and is `aria-hidden`: each sits beside a word that says
// the same thing, so a screen reader is told once and not twice. None of
// them carries information of its own — that is SPEC 11.22, and it is why
// the clock sits beside the time and not instead of it.

/** The site's mark: a cloud with three drops under it. Also the favicon. */
export function Logo({ className = 'icon logo' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true"
      focusable="false">
      <path
        d="M7 14.5h9.5a3.5 3.5 0 0 0 .2-7 5 5 0 0 0-9.5-.8A3.9 3.9 0 0 0 7
           14.5Z"
        fill="currentColor"
      />
      <g stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        <path d="M9 17.5v2.2" />
        <path d="M12.5 17.5v3.2" />
        <path d="M16 17.5v2.2" />
      </g>
    </svg>
  );
}

/** Beside the freshness line, which says the time in words next to it. */
export function Clock({ className = 'icon' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true"
      focusable="false" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round">
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 7.4V12l3.2 2.2" />
    </svg>
  );
}

/** Beside "Not an official warning", which says it in words. */
export function Warn({ className = 'icon' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true"
      focusable="false" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round">
      <path d="M12 3.6 1.9 20.4h20.2L12 3.6Z" />
      <path d="M12 9.6v4.6" />
      <path d="M12 17.2h.01" />
    </svg>
  );
}

/** On the button whose accessible name is "Use my location". */
export function Pin({ className = 'icon' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true"
      focusable="false" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round">
      <path d="M12 21.2s6.4-6.1 6.4-10.6a6.4 6.4 0 1 0-12.8 0C5.6 15.1 12
               21.2 12 21.2Z" />
      <circle cx="12" cy="10.4" r="2.4" />
    </svg>
  );
}

/** On the Menu button, which carries the word "Menu" beside it. */
export function Bars({ className = 'icon' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true"
      focusable="false" fill="none" stroke="currentColor" strokeWidth="1.9"
      strokeLinecap="round">
      <path d="M3.8 7h16.4" />
      <path d="M3.8 12h16.4" />
      <path d="M3.8 17h16.4" />
    </svg>
  );
}
