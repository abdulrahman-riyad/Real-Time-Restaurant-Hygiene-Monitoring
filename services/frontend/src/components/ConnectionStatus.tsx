'use client'

import { useStore } from '@/lib/store'
import { Wifi, WifiOff } from 'lucide-react'

export default function ConnectionStatus() {
  const isConnected = useStore((state) => state.isConnected)

  return (
    <div className="flex items-center space-x-2">
      {isConnected ? (
        <>
          <Wifi className="h-5 w-5 text-green-500" />
          <span className="text-sm text-green-600">Connected</span>
        </>
      ) : (
        <>
          <WifiOff className="h-5 w-5 text-red-500" />
          <span className="text-sm text-red-600">Disconnected</span>
        </>
      )}
    </div>
  )
}