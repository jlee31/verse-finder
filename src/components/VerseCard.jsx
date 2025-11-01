/**
 * VerseCard Component
 * 
 * Reusable UI component for displaying Bible verses with metadata
 * Features: verse text, reference, relevance score, theme badges
 */
import { useNavigate } from 'react-router-dom'

function VerseCard({ verse, showScore = true, clickable = true }) {
  const navigate = useNavigate()

  const handleClick = () => {
    if (clickable) {
      navigate(`/verse/${encodeURIComponent(verse.reference)}`)
    }
  }

  return (
    <div 
      className={`bg-white rounded-lg shadow-md p-6 border-l-4 border-purple-500 transition-all hover:shadow-lg ${
        clickable ? 'cursor-pointer hover:scale-[1.02]' : ''
      }`}
      onClick={handleClick}
    >
      {/* Verse Reference Header */}
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-xl font-bold text-purple-700">
          {verse.reference}
        </h3>
        {showScore && verse.relevanceScore && (
          <div className="flex items-center gap-1 bg-purple-100 px-3 py-1 rounded-full">
            <span className="text-sm font-semibold text-purple-700">
              {Math.round(verse.relevanceScore * 100)}%
            </span>
            <span className="text-xs text-purple-600">match</span>
          </div>
        )}
      </div>

      {/* Verse Text */}
      <blockquote className="text-gray-700 leading-relaxed mb-4 italic border-l-2 border-purple-200 pl-4">
        "{verse.text}"
      </blockquote>

      {/* Theme Badge (if available) */}
      {verse.theme && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Theme:</span>
          <span className="inline-block bg-blue-100 text-blue-700 px-3 py-1 rounded-full text-xs font-medium capitalize">
            {verse.theme}
          </span>
        </div>
      )}

      {/* Book Info */}
      <div className="mt-3 pt-3 border-t border-gray-200">
        <p className="text-sm text-gray-600">
          📖 {verse.book} {verse.chapter}:{verse.verse}
        </p>
      </div>
    </div>
  )
}

export default VerseCard
