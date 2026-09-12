import { lazy, Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { ApiError } from './api/client'
import { Layout } from './components/Layout'
import { ThemeProvider } from './lib/theme'
import { BlockSkeleton, Empty } from './components/ui'
import { AlertDetailPage } from './pages/AlertDetailPage'
import { AskPage } from './pages/AskPage'
import { OverviewPage } from './pages/OverviewPage'
import { QueuePage } from './pages/QueuePage'

// force-graph is ~600kB; only the account page needs it eagerly
const AccountGraphPage = lazy(() => import('./pages/AccountGraphPage').then((m) => ({ default: m.AccountGraphPage })))

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      // one retry for network blips / 5xx; a 4xx will not change its mind
      retry: (n, err) => n < 1 && !(err instanceof ApiError && err.status >= 400 && err.status < 500),
    },
  },
})

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <QueuePage /> },
      { path: 'overview', element: <OverviewPage /> },
      { path: 'ask', element: <AskPage /> },
      { path: 'alerts/:id', element: <AlertDetailPage /> },
      { path: 'accounts/:id', element: <Suspense fallback={<BlockSkeleton lines={6} />}><AccountGraphPage /></Suspense> },
      { path: '*', element: <Empty icon="search_off" title="Not found" /> },
    ],
  },
])

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={qc}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>
  )
}
