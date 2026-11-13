// Three pages behind one index.html. SPEC 11.34.
//
// The forecast is the whole window: a map that fills the screen with a panel
// beside it. The other two are documents: a column of text that scrolls. So
// the shell is not shared beyond the menu, and each page keeps the shape its
// own job needs.
//
// The two document pages are lazy, which is what keeps How we checked's
// 126 KB of working out of the forecast's download.

import { Suspense, lazy } from 'react';

import App, { Footer } from './App.jsx';
import TopNav, { plainClick, usePath } from './TopNav';

const ReportCard = lazy(() => import('./ReportCard'));
const HowWeChecked = lazy(() => import('./HowWeChecked'));

export default function Site() {
  const [path, go] = usePath();
  const nav = <TopNav path={path} onGo={go} />;
  if (path === '/') return <App nav={nav} />;
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
            India rain forecast
          </a>
        </p>
        {nav}
      </header>
      <main>
        <Suspense
          fallback={<p className="loading">Reading the track record…</p>}
        >
          {path === '/report-card' ? <ReportCard /> : <HowWeChecked />}
        </Suspense>
      </main>
      <Footer />
    </div>
  );
}
