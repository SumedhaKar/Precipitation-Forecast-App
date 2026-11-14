// Four pages behind one index.html. SPEC 11.34, remade by 11.39.
//
// The site is a header and a page under it. The header is the same on all
// four -- the mark, the name, how old this run is, the menu, and the
// warning -- because two of those are rules about every page and not about
// the forecast: freshness and "not an official warning" are on the first
// screen wherever a reader lands.
//
// The forecast is a grid of five blocks that scrolls; the other three are
// documents, a column of text that scrolls. So nothing below the header is
// shared, and each page keeps the shape its own job needs.
//
// The three document pages are lazy, which is what keeps How we checked's
// 126 KB of working out of the forecast's download.

import { Suspense, lazy, useEffect, useState } from 'react';

import App, { Footer, PageHead } from './App.jsx';
import TopNav, { titleOf, usePath } from './TopNav';

const ReportCard = lazy(() => import('./ReportCard'));
const HowWeChecked = lazy(() => import('./HowWeChecked'));
const HowToRead = lazy(() => import('./HowToRead'));

/** Which document page a path is. SPEC 11.39. */
function docFor(path) {
  if (path === '/report-card') return <ReportCard />;
  if (path === '/how-we-checked') return <HowWeChecked />;
  return <HowToRead />;
}

export default function Site() {
  const [path, go] = usePath();
  // SPEC 11.39. One request to our own origin, here rather than in the
  // forecast page, because the header of every page is built from it: the
  // run, the day labels, the staleness, and where the store is.
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);
  useEffect(() => {
    let alive = true;
    fetch('/api/health')
      .then((response) => response.json())
      .then((body) => {
        if (!alive) return;
        if (body.ok) setHealth(body);
        else setHealthError(body.store || 'the store could not be read');
      })
      .catch((error) => alive && setHealthError(error.message));
    return () => { alive = false; };
  }, []);
  // SPEC 11.38. The tab is the page's own, and it follows pushState: the
  // menu changes the path without a navigation, so nothing else would.
  useEffect(() => { document.title = titleOf(path); }, [path]);
  const nav = <TopNav path={path} onGo={go} />;
  return (
    <div className="shell">
      <PageHead run={health} nav={nav} onGo={go} />
      {path === '/' ? (
        <App health={health} healthError={healthError} onGo={go} />
      ) : (
        <div className="doc">
          <main>
            <Suspense
              fallback={(
                <p className="loading">
                  {path === '/how-to-read' ? 'Opening the page…'
                    : 'Reading the track record…'}
                </p>
              )}
            >
              {docFor(path)}
            </Suspense>
          </main>
          <Footer />
        </div>
      )}
    </div>
  );
}
