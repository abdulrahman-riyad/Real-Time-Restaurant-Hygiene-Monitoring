'use client'

import { useState } from 'react'
import { useStore } from '@/lib/store'
import VideoStream from './VideoStream'
import ViolationsList from './ViolationsList'
import StreamControls from './StreamControls'
import ConnectionStatus from './ConnectionStatus'
import { Activity, AlertTriangle } from 'lucide-react'

// Define available video files
const AVAILABLE_VIDEO_FILES = [
  'Sah w b3dha ghalt.mp4',
  'Sah w b3dha ghalt (2).mp4',
  'Sah w b3dha ghalt (3).mp4',
];

export default function Dashboard() {
  const { streams, violations } = useStore();
  
  // Start with no stream selected. It will be set when the user
  // clicks the "Start New Stream" button.
  const [selectedStreamId, setSelectedStreamId] = useState<string | null>(null);

  const [selectedVideoFile, setSelectedVideoFile] = useState<string>(AVAILABLE_VIDEO_FILES[0]);

  // If a stream is selected, get its data.
  const currentStreamData = selectedStreamId ? streams.get(selectedStreamId) : null;

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <h1 className="text-2xl font-bold text-gray-900">Pizza Store Monitoring System</h1>
            <ConnectionStatus />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats Overview */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <div className="bg-white rounded-lg shadow p-4 flex items-center space-x-4">
                <div className="bg-blue-100 p-3 rounded-full"><Activity className="h-6 w-6 text-blue-500" /></div>
                <div>
                    <p className="text-sm text-gray-500">Active Streams</p>
                    <p className="text-2xl font-semibold">{streams.size}</p>
                </div>
            </div>
            <div className="bg-white rounded-lg shadow p-4 flex items-center space-x-4">
                <div className="bg-red-100 p-3 rounded-full"><AlertTriangle className="h-6 w-6 text-red-500" /></div>
                <div>
                    <p className="text-sm text-gray-500">Total Violations</p>
                    <p className="text-2xl font-semibold">{violations.length}</p>
                </div>
            </div>
             <div className="bg-white rounded-lg shadow p-4">
                 <p className="text-sm text-gray-500">Current FPS</p>
                 <p className="text-2xl font-semibold">{currentStreamData?.stats.fps.toFixed(1) || '0.0'}</p>
             </div>
             <div className="bg-white rounded-lg shadow p-4">
                 <p className="text-sm text-gray-500">Stream Violations</p>
                 <p className="text-2xl font-semibold">{currentStreamData?.stats.violations_count || 0}</p>
             </div>
        </div>

        {/* Stream Controls */}
        <StreamControls
          availableVideos={AVAILABLE_VIDEO_FILES}
          selectedVideo={selectedVideoFile}
          onVideoSelect={setSelectedVideoFile}
          // This callback sets the active stream ID for the whole dashboard
          onStreamStart={(newStreamId) => setSelectedStreamId(newStreamId)}
          onStreamStop={() => setSelectedStreamId(null)}
        />

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mt-8">
          <div className="lg:col-span-2">
            {/* Conditionally render the VideoStream only when a stream is selected */}
            {selectedStreamId ? (
              <VideoStream streamId={selectedStreamId} />
            ) : (
              <div className="bg-white rounded-lg shadow-lg h-[540px] flex items-center justify-center text-gray-500">
                <p>Select a video and click "Start New Stream" to begin monitoring.</p>
              </div>
            )}
          </div>
          <div className="lg:col-span-1">
            <ViolationsList violations={violations} />
          </div>
        </div>
      </main>
    </div>
  )
}