'use client'

import { type Violation } from '@/lib/store'
import { AlertTriangle, Clock, User } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

interface ViolationsListProps {
  violations: Violation[]
}

export default function ViolationsList({ violations }: ViolationsListProps) {
  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'high': return 'text-red-600 bg-red-100';
      case 'medium': return 'text-yellow-600 bg-yellow-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  }

  return (
    <div className="bg-white rounded-lg shadow-lg">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900 flex items-center">
          <AlertTriangle className="h-5 w-5 mr-2 text-red-500" />
          Recent Violations
        </h3>
      </div>
      <div className="max-h-[600px] overflow-y-auto">
        {violations.length === 0 ? (
          <div className="px-6 py-8 text-center text-gray-500">
            <AlertTriangle className="h-12 w-12 mx-auto mb-4 text-gray-300" />
            <p>No violations detected</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {violations.map((violation) => (
              <div key={violation.id} className="px-6 py-4">
                <div className="flex items-center space-x-2 mb-1">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getSeverityColor(violation.severity)}`}>
                    {violation.severity.toUpperCase()}
                  </span>
                  <span className="text-xs text-gray-500">
                    {violation.stream_id || 'Unknown Stream'}
                  </span>
                </div>
                <p className="text-sm text-gray-900 font-medium">{violation.message}</p>
                <div className="mt-2 flex items-center space-x-4 text-xs text-gray-500">
                  <span className="flex items-center">
                    <Clock className="h-3 w-3 mr-1" />
                    {formatDistanceToNow(new Date(violation.timestamp * 1000), { addSuffix: true })}
                  </span>
                  <span className="flex items-center">
                    <User className="h-3 w-3 mr-1" />
                    {violation.person_id || 'Unknown Person'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}