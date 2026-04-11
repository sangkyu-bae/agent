import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { authService } from '@/services/authService';
import { useAuthStore } from '@/store/authStore';
import { queryKeys } from '@/lib/queryKeys';
import type { LoginRequest, RegisterRequest } from '@/types/auth';

export const useMe = () => {
  const { isAuthenticated } = useAuthStore();
  return useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: authService.me,
    enabled: isAuthenticated,
    retry: false,
  });
};

export const useInitAuth = () => {
  const { refreshToken, setAuth, updateAccessToken } = useAuthStore();

  return useQuery({
    queryKey: queryKeys.auth.init(),
    queryFn: async () => {
      if (!refreshToken) return null;
      const { access_token } = await authService.refresh(refreshToken);
      updateAccessToken(access_token); // store에 먼저 주입 → me() 요청 시 헤더에 포함됨
      const user = await authService.me();
      setAuth(user, access_token, refreshToken);
      return user;
    },
    enabled: !!refreshToken,
    retry: false,
    staleTime: Infinity,
  });
};

export const useLogin = () => {
  const { setAuth, updateAccessToken } = useAuthStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: LoginRequest) => authService.login(data),
    onSuccess: async (tokens) => {
      updateAccessToken(tokens.access_token); // store에 먼저 주입 → me() 요청 시 헤더에 포함됨
      const user = await authService.me();
      setAuth(user, tokens.access_token, tokens.refresh_token);
      queryClient.invalidateQueries({ queryKey: queryKeys.auth.me() });
      navigate('/');
    },
  });
};

export const useRegister = () =>
  useMutation({
    mutationFn: (data: RegisterRequest) => authService.register(data),
  });

export const useLogout = () => {
  const { refreshToken, logout } = useAuthStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => authService.logout(refreshToken ?? ''),
    onSettled: () => {
      logout();
      queryClient.clear();
      navigate('/login');
    },
  });
};
