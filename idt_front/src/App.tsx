import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import TopNav from '@/components/layout/TopNav';
import ChatPage from '@/pages/ChatPage';
import DocumentPage from '@/pages/DocumentPage';
import EvalDatasetPage from '@/pages/EvalDatasetPage';
import AgentBuilderPage from '@/pages/AgentBuilderPage';
import ToolConnectionPage from '@/pages/ToolConnectionPage';
import ToolAdminPage from '@/pages/ToolAdminPage';
import WorkflowDesignerPage from '@/pages/WorkflowDesignerPage';
import WorkflowBuilderPage from '@/pages/WorkflowBuilderPage';

const App = () => (
  <BrowserRouter>
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <TopNav />
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <Routes>
          <Route path="/" element={<Navigate to="/chatpage" replace />} />
          <Route path="/chatpage" element={<ChatPage />} />
          <Route path="/documents" element={<DocumentPage />} />
          <Route path="/eval-dataset" element={<EvalDatasetPage />} />
          <Route path="/agent-builder" element={<AgentBuilderPage />} />
          <Route path="/tool-connection" element={<ToolConnectionPage />} />
          <Route path="/tool-admin" element={<ToolAdminPage />} />
          <Route path="/workflow-designer" element={<WorkflowDesignerPage />} />
          <Route path="/workflow-builder" element={<WorkflowBuilderPage />} />
        </Routes>
      </div>
    </div>
  </BrowserRouter>
);

export default App;
