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
import KnowledgeBasesPage from '@/pages/KnowledgeBasesPage';
import KnowledgeBaseDetailPage from '@/pages/KnowledgeBaseDetailPage';
import LoginPage from '@/pages/LoginPage';
import RegisterPage from '@/pages/RegisterPage';
import AdminUsersPage from '@/pages/AdminUsersPage';
import AdminDepartmentsPage from '@/pages/AdminDepartmentsPage';
import AdminMcpServersPage from '@/pages/AdminMcpServersPage';
import AdminLlmModelsPage from '@/pages/AdminLlmModelsPage';
import AdminChunkingProfilesPage from '@/pages/AdminChunkingProfilesPage';
import AdminSkillsPage from '@/pages/AdminSkillsPage';
import AdminRagasPage from '@/pages/AdminRagasPage';
import AdminAgentRunsPage from '@/pages/AdminAgentRunsPage';
import AdminDashboardPage from '@/pages/AdminDashboardPage';
import WikiPage from '@/pages/WikiPage';
import AgentKnowledgePage from '@/pages/AgentKnowledgePage';
import KnowledgeArticlePage from '@/pages/KnowledgeArticlePage';
import AgentRunDetailPage from '@/pages/AgentRunDetailPage';
import UsageMePage from '@/pages/UsageMePage';
import SettingsPage from '@/pages/SettingsPage';
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
          <Route path="/knowledge-bases" element={<KnowledgeBasesPage />} />
          <Route path="/knowledge-bases/:kbId" element={<KnowledgeBaseDetailPage />} />
          {/* wiki-user-facing: 에이전트 지식 브라우저 + 문서 단독 뷰 */}
          <Route path="/agents/:agentId/knowledge" element={<AgentKnowledgePage />} />
          <Route path="/knowledge/:articleId" element={<KnowledgeArticlePage />} />
          <Route path="/usage" element={<UsageMePage />} />
          {/* agent-memory: AI 메모리 관리 */}
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>

      {/* Admin 전용 라우트 */}
      <Route element={<AdminRoute />}>
        <Route element={<AdminLayout />}>
          <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
          <Route path="/admin/users" element={<AdminUsersPage />} />
          <Route path="/admin/departments" element={<AdminDepartmentsPage />} />
          <Route path="/admin/mcp-servers" element={<AdminMcpServersPage />} />
          <Route path="/admin/llm-models" element={<AdminLlmModelsPage />} />
          <Route path="/admin/chunking-profiles" element={<AdminChunkingProfilesPage />} />
          <Route path="/admin/skills" element={<AdminSkillsPage />} />
          <Route path="/admin/ragas" element={<AdminRagasPage />} />
          <Route path="/admin/agent-runs" element={<AdminAgentRunsPage />} />
          <Route path="/admin/agent-runs/:runId" element={<AgentRunDetailPage />} />
          <Route path="/admin/wiki" element={<WikiPage />} />
        </Route>
      </Route>

    </Routes>
    </AuthInitializer>
  </BrowserRouter>
);

export default App;
