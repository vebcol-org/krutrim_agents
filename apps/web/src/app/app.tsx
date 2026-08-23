import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Agent } from '@krutrim_agent/agent-ui';
import { DEFAULT_BACKEND_URL } from '@krutrim_agent/shared-types';

const backendUrl = import.meta.env['VITE_BACKEND_URL'] ?? DEFAULT_BACKEND_URL;

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Agent backendUrl={backendUrl} />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
