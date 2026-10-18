import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

export type Me = { id: number; username: string; display_name: string; role: 'viewer' | 'analyst' | 'admin'; must_change_password: boolean }

type AuthCtx = { me: Me | null; loading: boolean; login: (u: string, p: string) => Promise<string | null>; logout: () => Promise<void>; refresh: () => Promise<void> }
const Ctx = createContext<AuthCtx>({ me: null, loading: true, login: async () => null, logout: async () => {}, refresh: async () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const refresh = useCallback(async () => {
    try {
      const r = await fetch('/api/auth/me')
      setMe(r.ok ? await r.json() : null)
    } catch { setMe(null) } finally { setLoading(false) }
  }, [])
  useEffect(() => { refresh() }, [refresh])
  const login = async (username: string, password: string) => {
    const r = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Rasad-Client': 'web' }, body: JSON.stringify({ username, password }) })
    if (!r.ok) { try { return (await r.json()).detail as string } catch { return `${r.status}` } }
    setMe(await r.json())
    return null
  }
  const logout = async () => { await fetch('/api/auth/logout', { method: 'POST', headers: { 'X-Rasad-Client': 'web' } }); setMe(null) }
  return <Ctx.Provider value={{ me, loading, login, logout, refresh }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
export const atLeast = (role: Me['role'] | undefined, min: Me['role']) => ({ viewer: 0, analyst: 1, admin: 2 }[role ?? 'viewer'] >= { viewer: 0, analyst: 1, admin: 2 }[min])
