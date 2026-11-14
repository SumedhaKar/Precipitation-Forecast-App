// The three pages, and how the page knows which one it is on. SPEC 11.34.
//
// Real paths, not hashes: /, /report-card and /how-we-checked can be linked
// to, bookmarked and sent to a reviewer, and `vercel.json` sends all three to
// the same index.html.
//
// The links are plain <a href>. A middle click opens a tab, a right click
// offers "copy link address", the keyboard reaches them with no handler of
// ours, and with JavaScript off they are still three working links to three
// paths. A plain left click is intercepted and becomes history.pushState,
// which is the only thing here that needs script at all.

import { useEffect, useState } from 'react';

// SPEC 11.38. The site's name, used wherever the site names itself: the
// heading, the back link on the two document pages, and all three browser
// tabs. One string, so a rename is one edit.
export const SITE = 'India Rain Outlook';

// SPEC 11.38. `title` is the browser tab. All three pages shared one title
// until now, so a reader with the forecast, the report card and How we
// checked open could not tell the three tabs apart.
export const PAGES = [
  { path: '/', name: 'Forecast', title: `${SITE} · next 5 days` },
  { path: '/report-card', name: 'Report card', title: `Report card · ${SITE}` },
  { path: '/how-we-checked',
    name: 'How we checked',
    title: `How we checked · ${SITE}` },
  // SPEC 11.39. The fourth page: everything that explains the map, which
  // used to be a block inside the forecast panel. It is reached by name
  // from the menu and from "What does mm mean?" under the amount buttons,
  // and it is not one of the three links the header writes out in full:
  // the header band has room for three, and this one is linked from the
  // page it explains.
  { path: '/how-to-read',
    name: 'How to read this map',
    title: `How to read this map · ${SITE}` },
];

// The three the header writes out as text. SPEC 11.39.
export const BAR = PAGES.slice(0, 3);

/** The browser tab for a path, with anything unknown reading as the forecast. */
export function titleOf(path) {
  const want = pageOf(path);
  return (PAGES.find((page) => page.path === want) || PAGES[0]).title;
}

/** The page a path is, with anything unknown reading as the forecast. */
export function pageOf(path) {
  const want = String(path || '/').replace(/\/+$/, '') || '/';
  const found = PAGES.find((page) => page.path === want);
  return found ? found.path : '/';
}

/** Is this click one the browser should keep? */
export function plainClick(event) {
  return !(event.defaultPrevented || event.button !== 0 || event.metaKey
    || event.ctrlKey || event.shiftKey || event.altKey);
}

/** The current path, kept in step with the back and forward buttons. */
export function usePath() {
  const [path, setPath] = useState(
    () => pageOf(typeof window === 'undefined' ? '/'
      : window.location.pathname));
  useEffect(() => {
    const back = () => setPath(pageOf(window.location.pathname));
    window.addEventListener('popstate', back);
    return () => window.removeEventListener('popstate', back);
  }, []);
  const go = (to) => {
    window.history.pushState({}, '', to);
    setPath(pageOf(to));
    window.scrollTo(0, 0);
  };
  return [path, go];
}

/**
 * A link to the report card. SPEC 11.38.
 *
 * A plain <a href>, so a middle click opens a tab and the keyboard reaches
 * it with no handler of ours; a plain left click becomes the pushState the
 * menu uses, where the page has one to offer. With no `onGo` -- which is
 * what the server renderer and the tests have -- it is simply a link, and
 * the path it points at is a real page either way (SPEC 11.34).
 */
export function ReportCardLink({ onGo, children }) {
  return (
    <a
      href="/report-card"
      onClick={(event) => {
        if (!onGo || !plainClick(event)) return;
        event.preventDefault();
        onGo('/report-card');
      }}
    >
      {children}
    </a>
  );
}

/**
 * A link to How to read this map. SPEC 11.39.
 *
 * The explanation used to be a block drawn in the panel, under whatever
 * else the panel was saying: three bullets, two colour lines and the three
 * amount nicknames, on the same screen as the answer. It is a page of its
 * own now, and this is how the forecast page points at it.
 *
 * `to` carries the fragment where there is one: "What does mm mean?" lands
 * on the amounts rather than at the top of the page.
 *
 * Both of these live here, with the menu, rather than in the card: the
 * card, the controls and the page's own footer all link to one or the
 * other, and a component in the card that the controls import is a circle
 * between two modules.
 */
export function HowToReadLink({ onGo, to = '/how-to-read', children }) {
  return (
    <a
      href={to}
      className="howtolink"
      onClick={(event) => {
        if (!onGo || !plainClick(event)) return;
        event.preventDefault();
        onGo(to);
      }}
    >
      {children || 'How to read this map'}
    </a>
  );
}

export default function TopNav({ path, onGo }) {
  return (
    <nav className="topnav" aria-label="The main pages">
      <ul>
        {BAR.map((page) => {
          const here = page.path === path;
          return (
            <li key={page.path}>
              <a
                href={page.path}
                className={here ? 'navlink here' : 'navlink'}
                aria-current={here ? 'page' : undefined}
                onClick={(event) => {
                  if (!plainClick(event)) return;
                  event.preventDefault();
                  onGo(page.path);
                }}
              >
                {page.name}
                {/* The colour is not the only thing that says which page
                    this is: SPEC 11.22. */}
                {here ? (
                  <span className="small hereword"> (you are here)</span>
                ) : null}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
