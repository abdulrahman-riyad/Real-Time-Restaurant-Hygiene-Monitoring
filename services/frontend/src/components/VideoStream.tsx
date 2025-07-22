'use client'

import { useStore } from '@/lib/store'
import { Camera } from 'lucide-react'
import { useEffect, useState } from 'react'

interface VideoStreamProps {
  streamId: string
}

export default function VideoStream({ streamId }: VideoStreamProps) {
  const streamData = useStore((state) => state.streams.get(streamId))
  const [imageSrc, setImageSrc] = useState('')

  useEffect(() => {
    if (streamData?.data?.annotated_frame_data) {
      setImageSrc(`data:image/jpeg;base64,${streamData.data.annotated_frame_data}`)
    }
  }, [streamData])

  return (
    <div className="bg-white rounded-lg shadow-lg overflow-hidden">
      <div className="bg-gray-800 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Camera className="h-5 w-5 text-white" />
          <h3 className="text-white font-medium">Stream: {streamId}</h3>
        </div>
        <div className="flex items-center space-x-4 text-sm text-gray-300">
          <span>FPS: {streamData?.stats?.fps.toFixed(1) || '0.0'}</span>
          <span>Violations: {streamData?.stats?.violations_count || 0}</span>
        </div>
      </div>

      <div className="relative w-full h-[480px] bg-black flex items-center justify-center">
        {imageSrc ? (
          <img
            src={imageSrc}
            alt={`Live stream for ${streamId}`}
            className="w-full h-full object-contain"
          />
        ) : (
          <div className="text-gray-500 text-center">
            <Camera className="h-16 w-16 mx-auto mb-4" />
            <p>No stream data available</p>
            <p className="text-sm mt-2">
              Waiting for stream... Ensure the stream is started.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}