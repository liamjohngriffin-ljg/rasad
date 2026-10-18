import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import './index.css'
import App from './App'
import { LangProvider } from './i18n'
import Board from './pages/Board'
import Question from './pages/Question'
import Positions from './pages/Positions'
import Record from './pages/Record'
import Queue from './pages/Queue'
import Sources from './pages/Sources'
import BriefPage from './pages/BriefPage'
import Users from './pages/Users'
import Account from './pages/Account'
import { AuthProvider } from './auth'

const router = createBrowserRouter([
  {
    path: '/', element: <App />,
    children: [
      { index: true, element: <Board /> },
      { path: 'q/:code', element: <Question /> },
      { path: 'q/:code/brief', element: <BriefPage /> },
      { path: 'positions', element: <Positions /> },
      { path: 'positions/:actor', element: <Positions /> },
      { path: 'record', element: <Record /> },
      { path: 'queue', element: <Queue /> },
      { path: 'sources', element: <Sources /> },
      { path: 'users', element: <Users /> },
      { path: 'account', element: <Account /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LangProvider>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </LangProvider>
  </StrictMode>,
)
