// Three pages behind one index.html. SPEC 11.34.
//
// The forecast is the whole window: a map that fills the screen with a panel
// beside it. The other two are documents: a column of text that scrolls. So
// the shell is not shared beyond the menu, and each page keeps the shape its
// own job needs.
//
// The two document pages are lazy, which is what keeps How we checked's
// 126 KB of working out of the forecast's download.

import { Suspense, lazy, useEffect } from 'react';

import App, { Footer } from './App.jsx';
import TopNav, { SITE, plainClick, titleOf, usePath } from './TopNav';

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
  // SPEC 11.38. The tab is the page's own, and it follows pushState: the
  // menu changes the path without a navigation, so nothing else would.
  useEffect(() => { document.title = titleOf(path); }, [path]);
  const nav = <TopNav path={path} onGo={go} />;
  if (path === '/') return <App nav={nav} onGo={go} />;
  return (
    <div className="doc">
      <header className="dochead">
        <p className="docback">
          <a
            href="/"
            onClick={(event) => {
              if (!plainClick(event)) return;
              event.preventDefault();
              go('/');
            }}
          >
            {SITE}
          </a>
        </p>
        {nav}
      </header>
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
  );
}
