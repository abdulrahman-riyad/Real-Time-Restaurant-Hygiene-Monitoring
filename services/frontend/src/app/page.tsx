'use client'

import { useEffect } from 'react'
import Dashboard from '@/components/Dashboard'
import { useStore } from '@/lib/store'

export default function Home() {
  const initializeConnection = useStore((state) => state.initializeConnection)
  
  useEffect(() => {
    initializeConnection()
  }, [initializeConnection])

  return (
    <main className="min-h-screen bg-gray-50">
      <Dashboard />
    </main>
  )
}