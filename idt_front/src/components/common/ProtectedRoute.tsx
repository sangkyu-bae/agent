import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { useInitAuth } from '@/hooks/useAuth';

const ProtectedRoute = () => {
  const { isAuthenticated, user, refreshToken } = useAuthStore();
  const { isLoading } = useInitAuth();

  if (!user && refreshToken && isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-zinc-400">
        로딩 중...
      </div>
    );
  }

  return isAuthenticated || user !== null ? <Outlet /> : <Navigate to="/login" replace />;
};

export default ProtectedRoute;
