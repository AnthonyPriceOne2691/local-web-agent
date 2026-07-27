import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';
import './index.css';

// Явная проверка вместо `!`: если #root пропал из index.html, ошибка должна
// называть причину, а не падать как «Cannot read properties of null».
const container = document.getElementById('root');
if (!container) {
  throw new Error('#root not found in index.html — cannot mount the app');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
