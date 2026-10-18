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
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LangProvider>
      <RouterProvider router={router} />
    </LangProvider>
  </StrictMode>,
)
