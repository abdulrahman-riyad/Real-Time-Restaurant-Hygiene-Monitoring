'use client'

import { useState } from 'react'
import { useStore } from '@/lib/store'
import { Play, StopCircle } from 'lucide-react'
import toast from 'react-hot-toast'

interface StreamControlsProps {
  availableVideos: string[]
  selectedVideo: string
  onVideoSelect: (videoFile: string) => void
  onStreamStart: (newStreamId: string) => void
  onStreamStop: () => void // Callback to tell the dashboard to clear the view
}

export default function StreamControls({
  availableVideos,
  selectedVideo,
  onVideoSelect,
  onStreamStart,
  onStreamStop,
}: StreamControlsProps) {
  const { isConnected } = useStore()
  const [isLoading, setIsLoading] = useState(false)
  const [activeStreamId, setActiveStreamId] = useState<string | null>(null)

  const handleStartStream = async () => {
    setIsLoading(true);

    try {
      // First, ensure any previous stream is fully stopped.
      await fetch('http://localhost:8000/api/stop-stream', { method: 'POST' });
      
      const newStreamId = `stream_${Date.now()}`;

      // Tell the backend to flush any lingering data for this old stream ID
      if (activeStreamId) {
        await fetch(`http://localhost:8000/api/flush-stream/${activeStreamId}`, { method: 'POST' });
      }

      const response = await fetch('http://localhost:8000/api/start-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_path: selectedVideo,
          stream_id: newStreamId,
        }),
      });

      if (response.ok) {
        toast.success(`Stream '${newStreamId}' started.`);
        setActiveStreamId(newStreamId);
        onStreamStart(newStreamId);
      } else {
        toast.error(`Failed to start stream.`);
      }
    } catch (error) {
      toast.error('An error occurred while starting the stream.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopStream = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/stop-stream', { method: 'POST' });
      if (response.ok) {
        toast.success("Stream stopped.");
        setActiveStreamId(null);
        onStreamStop(); // Tell the dashboard to clear the video player
      } else {
        toast.error("Failed to stop stream.");
      }
    } catch (error) {
      toast.error("Error stopping stream.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex flex-col md:flex-row items-center justify-between space-y-4 md:space-y-0">
        <div className="flex items-center space-x-4">
          <label htmlFor="video-select" className="text-sm font-medium text-gray-700">Source Video:</label>
          <select
            id="video-select"
            value={selectedVideo}
            onChange={(e) => onVideoSelect(e.target.value)}
            // Disable the dropdown while a stream is active to prevent confusion
            disabled={!!activeStreamId}
            className="block w-full md:w-64 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
          >
            {availableVideos.map((videoFile) => (
              <option key={videoFile} value={videoFile}>
                {videoFile}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={handleStartStream}
            // Disable button if not connected, loading, OR if a stream is already active
            disabled={!isConnected || isLoading || !!activeStreamId}
            className="inline-flex items-center justify-center w-full md:w-auto px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play className="h-4 w-4 mr-2" />
            {isLoading && !activeStreamId ? 'Starting...' : 'Start New Stream'}
          </button>
          
          <button
            onClick={handleStopStream}
            // Disable button if not connected, loading, OR if NO stream is active
            disabled={!isConnected || isLoading || !activeStreamId}
            className="inline-flex items-center justify-center w-full md:w-auto px-4 py-2 border border-gray-300 text-sm font-medium rounded-md shadow-sm text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <StopCircle className="h-4 w-4 mr-2" />
            {isLoading && activeStreamId ? 'Stopping...' : 'Stop Stream'}
          </button>
        </div>
      </div>
    </div>
  )
}