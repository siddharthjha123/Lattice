import { create } from "zustand";
import { getAuthToken, setAuthToken, verifyOperator } from "@/lib/api/client";
interface UserProfile {
  name: string;
  email: string;
  workspace: string;
}
interface AuthState {
  user: UserProfile;
  token: string;
  isAuthenticated: boolean;
  hydrated: boolean;
  preview: boolean;
  setUser: (user: Partial<UserProfile>) => void;
  setToken: (token: string) => void;
  hydrate: () => Promise<void>;
  login: (token: string, name: string) => Promise<void>;
  explore: () => void;
  logout: () => void;
}
export const useAuthStore = create<AuthState>((set, get) => ({
  user: { name: "Operator", email: "", workspace: "Controller workspace" },
  token: "",
  isAuthenticated: false,
  hydrated: false,
  preview: false,
  setUser: (updates) => set((s) => ({ user: { ...s.user, ...updates } })),
  setToken: (token) => {
    setAuthToken(token);
    set({ token, isAuthenticated: !!token, preview: false });
  },
  hydrate: async () => {
    if (get().hydrated) return;
    const token = getAuthToken();
    if (token) {
      try {
        await verifyOperator(token);
        set({ token, isAuthenticated: true });
      } catch {
        setAuthToken("");
      }
    }
    set({ hydrated: true });
  },
  login: async (token, name) => {
    await verifyOperator(token);
    setAuthToken(token.trim());
    set((s) => ({
      token: token.trim(),
      user: { ...s.user, name: name.trim() || "Operator" },
      isAuthenticated: true,
      hydrated: true,
      preview: false,
    }));
  },
  explore: () => {
    setAuthToken("");
    set({ token: "", isAuthenticated: false, hydrated: true, preview: true });
  },
  logout: () => {
    setAuthToken("");
    set({ token: "", isAuthenticated: false, preview: false, hydrated: true });
  },
}));
export function useOperatorSession() {
  return useAuthStore((s) => s.isAuthenticated && !s.preview);
}
