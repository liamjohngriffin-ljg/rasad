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
import Questions from './pages/Questions'
import Evidence from './pages/Evidence'
import Tasking from './pages/Tasking'
import Today from './pages/Today'
import Search from './pages/Search'
import Admin from './pages/Admin'
import MapPage from './pages/MapPage'
import WeeklyBrief from './pages/WeeklyBrief'
import SeriesPage from './pages/SeriesPage'
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
      { path: 'questions', element: <Questions /> },
      { path: 'evidence', element: <Evidence /> },
      { path: 'tasking', element: <Tasking /> },
      { path: 'today', element: <Today /> },
      { path: 'search', element: <Search /> },
      { path: 'admin', element: <Admin /> },
      { path: 'map', element: <MapPage /> },
      { path: 'weekly', element: <WeeklyBrief /> },
      { path: 'series', element: <SeriesPage /> },
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
