import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AgentChatLayout from '@/components/layout/AgentChatLayout';
import ProtectedRoute from '@/components/common/ProtectedRoute';
import AdminRoute from '@/components/common/AdminRoute';
import ChatPage from '@/pages/ChatPage';
import EvalDatasetPage from '@/pages/EvalDatasetPage';
import AgentBuilderPage from '@/pages/AgentBuilderPage';
import ToolConnectionPage from '@/pages/ToolConnectionPage';
import ToolAdminPage from '@/pages/ToolAdminPage';
import WorkflowDesignerPage from '@/pages/WorkflowDesignerPage';
import WorkflowBuilderPage from '@/pages/WorkflowBuilderPage';
import AgentStorePage from '@/pages/AgentStorePage';
import CollectionPage from '@/pages/CollectionPage';
import CollectionDocumentsPage from '@/pages/CollectionDocumentsPage';
import LoginPage from '@/pages/LoginPage';
import RegisterPage from '@/pages/RegisterPage';
import AdminUsersPage from '@/pages/AdminUsersPage';
import AdminDepartmentsPage from '@/pages/AdminDepartmentsPage';
import AdminLayout from '@/components/layout/AdminLayout';
import { useInitAuth } from '@/hooks/useAuth';

const AuthInitializer = ({ children }: { children: React.ReactNode }) => {
  useInitAuth();
  return <>{children}</>;
};

const App = () => (
  <BrowserRouter>
    <AuthInitializer>
    <Routes>
      {/* 공개 라우트 */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* 인증 필요 라우트 */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AgentChatLayout />}>
          <Route path="/" element={<Navigate to="/chatpage" replace />} />
          <Route path="/chatpage" element={<ChatPage />} />
          <Route path="/documents" element={<Navigate to="/collections" replace />} />
          <Route path="/eval-dataset" element={<EvalDatasetPage />} />
          <Route path="/agent-builder" element={<AgentBuilderPage />} />
          <Route path="/tool-connection" element={<ToolConnectionPage />} />
          <Route path="/tool-admin" element={<ToolAdminPage />} />
          <Route path="/workflow-designer" element={<WorkflowDesignerPage />} />
          <Route path="/workflow-builder" element={<WorkflowBuilderPage />} />
          <Route path="/agent-store" element={<AgentStorePage />} />
          <Route path="/collections" element={<CollectionPage />} />
          <Route path="/collections/:collectionName/documents" element={<CollectionDocumentsPage />} />
        </Route>
      </Route>

      {/* Admin 전용 라우트 */}
      <Route element={<AdminRoute />}>
        <Route element={<AdminLayout />}>
          <Route path="/admin/users" element={<AdminUsersPage />} />
          <Route path="/admin/departments" element={<AdminDepartmentsPage />} />
        </Route>
      </Route>

    </Routes>
    </AuthInitializer>
  </BrowserRouter>
);

export default App;
