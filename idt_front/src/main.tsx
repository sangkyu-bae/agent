import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '@/lib/queryClient';
// Design Ref: ui-redesign-chat §5.0 — 폰트 CSS는 Tailwind 바깥에서 로드(index.css 주석 참조)
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css';
import './index.css';
import App from './App.tsx';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
