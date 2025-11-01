/**
 * ReflectionCard Component
 * 
 * Reusable UI component for displaying AI-generated reflections and spiritual insights
 * Features: reflection text, action points, encouragement messages
 */
import { useState } from 'react'

function ReflectionCard({ reflection, verses = [] }) {
  const [isExpanded, setIsExpanded] = useState(true)

  if (!reflection) {
    return null
  }

  return (
    <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-lg shadow-md p-6 border border-amber-200">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="text-3xl">✨</div>
          <h3 className="text-2xl font-bold text-gray-800">
            {reflection.title || 'Reflection'}
          </h3>
        </div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-gray-600 hover:text-gray-800 p-2 hover:bg-white rounded-full transition"
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
        >
          {isExpanded ? '▼' : '▶'}
        </button>
      </div>

      {isExpanded && (
        <div className="space-y-4">
          {/* Main Reflection Content */}
          {reflection.content && (
            <div className="bg-white bg-opacity-70 rounded-lg p-4 border border-amber-100">
              <p className="text-gray-700 leading-relaxed">
                {reflection.content}
              </p>
            </div>
          )}

          {/* Action Points */}
          {reflection.actionPoints && reflection.actionPoints.length > 0 && (
            <div>
              <h4 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
                <span>🎯</span>
                Action Steps:
              </h4>
              <ul className="space-y-2">
                {reflection.actionPoints.map((point, index) => (
                  <li key={index} className="flex items-start gap-3 bg-white bg-opacity-70 rounded-lg p-3 border border-amber-100">
                    <span className="text-orange-600 font-bold mt-0.5">{index + 1}.</span>
                    <span className="text-gray-700 flex-1">{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Encouragement Section */}
          {reflection.encouragement && (
            <div className="bg-gradient-to-r from-purple-100 to-pink-100 rounded-lg p-4 border border-purple-200">
              <div className="flex items-start gap-3">
                <span className="text-2xl">💝</span>
                <div>
                  <h4 className="font-semibold text-purple-900 mb-1">Encouragement</h4>
                  <p className="text-purple-800 italic">
                    {reflection.encouragement}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Related Verses Count */}
          {verses.length > 0 && (
            <div className="text-center pt-2">
              <p className="text-sm text-gray-600">
                Based on {verses.length} relevant verse{verses.length !== 1 ? 's' : ''}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default ReflectionCard
