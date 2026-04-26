import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import TopNav from '@/components/layout/TopNav';
import ProtectedRoute from '@/components/common/ProtectedRoute';
import AdminRoute from '@/components/common/AdminRoute';
import ChatPage from '@/pages/ChatPage';
import DocumentPage from '@/pages/DocumentPage';
import EvalDatasetPage from '@/pages/EvalDatasetPage';
import AgentBuilderPage from '@/pages/AgentBuilderPage';
import ToolConnectionPage from '@/pages/ToolConnectionPage';
import ToolAdminPage from '@/pages/ToolAdminPage';
import WorkflowDesignerPage from '@/pages/WorkflowDesignerPage';
import WorkflowBuilderPage from '@/pages/WorkflowBuilderPage';
import CollectionPage from '@/pages/CollectionPage';
import CollectionDocumentsPage from '@/pages/CollectionDocumentsPage';
import LoginPage from '@/pages/LoginPage';
import RegisterPage from '@/pages/RegisterPage';
import AdminUsersPage from '@/pages/AdminUsersPage';
import { useInitAuth } from '@/hooks/useAuth';

// 앱 마운트 시 refreshToken → accessToken 복원 (BrowserRouter 내부여야 useNavigate 사용 가능)
const AuthInitializer = ({ children }: { children: React.ReactNode }) => {
  useInitAuth();
  return <>{children}</>;
};

// TopNav를 포함한 인증된 레이아웃
const AuthenticatedLayout = () => (
  <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
    <TopNav />
    <div style={{ flex: 1, overflow: 'auto' }}>
      <Outlet />
    </div>
  </div>
);

const App = () => (
  <BrowserRouter>
    <AuthInitializer>
    <Routes>
      {/* 공개 라우트 */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* 인증 필요 라우트 */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AuthenticatedLayout />}>
          <Route path="/" element={<Navigate to="/chatpage" replace />} />
          <Route path="/chatpage" element={<ChatPage />} />
          <Route path="/documents" element={<Navigate to="/collections" replace />} />
          <Route path="/eval-dataset" element={<EvalDatasetPage />} />
          <Route path="/agent-builder" element={<AgentBuilderPage />} />
          <Route path="/tool-connection" element={<ToolConnectionPage />} />
          <Route path="/tool-admin" element={<ToolAdminPage />} />
          <Route path="/workflow-designer" element={<WorkflowDesignerPage />} />
          <Route path="/workflow-builder" element={<WorkflowBuilderPage />} />
          <Route path="/collections" element={<CollectionPage />} />
          <Route path="/collections/:collectionName/documents" element={<CollectionDocumentsPage />} />
        </Route>
      </Route>


      {/* Admin 전용 라우트 */}
      <Route element={<AdminRoute />}>
        <Route path="/admin/users" element={<AdminUsersPage />} />
      </Route>
     
    </Routes>
    </AuthInitializer>
  </BrowserRouter>
);

export default App;
