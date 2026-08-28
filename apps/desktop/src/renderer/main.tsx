import { StrictMode } from 'react';
import * as ReactDOM from 'react-dom/client';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Agent } from '@krutrim_agent/agent-ui';
import { DEFAULT_BACKEND_URL } from '@krutrim_agent/shared-types';

import './styles.css';

const backendUrl = import.meta.env['VITE_BACKEND_URL'] ?? DEFAULT_BACKEND_URL;

const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement);

root.render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        {/* Catch-all: `<Agent>` owns URL <-> workspace sync internally (see `useUrlSync`). */}
        <Route path="/*" element={<Agent backendUrl={backendUrl} />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
