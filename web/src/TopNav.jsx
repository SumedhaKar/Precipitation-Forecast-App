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
];

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

export default function TopNav({ path, onGo }) {
  return (
    <nav className="topnav" aria-label="The three pages">
      <ul>
        {PAGES.map((page) => {
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
                {here ? <span className="small"> (you are here)</span> : null}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
