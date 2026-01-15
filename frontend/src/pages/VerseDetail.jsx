/**
 * VerseDetail Page Component
 * 
 * Displays detailed information about a specific Bible verse
 * Features: verse context, related verses, themes, navigation
 */
import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getVerseDetails } from '../services/verseService'

function VerseDetail() {
  const { reference } = useParams()
  const navigate = useNavigate()
  const [verse, setVerse] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchVerseDetails = async () => {
      setIsLoading(true)
      setError(null)
      
      try {
        const result = await getVerseDetails(decodeURIComponent(reference))
        if (result.success) {
          setVerse(result.verse)
        } else {
          setError('Failed to load verse details')
        }
      } catch (err) {
        console.error('Error fetching verse details:', err)
        setError('An error occurred while loading the verse')
      } finally {
        setIsLoading(false)
      }
    }

    if (reference) {
      fetchVerseDetails()
    }
  }, [reference])

  const handleBack = () => {
    navigate(-1)
  }

  const handleRelatedVerseClick = (ref) => {
    navigate(`/verse/${encodeURIComponent(ref)}`)
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-purple-600 mx-auto mb-4"></div>
          <p className="text-xl text-gray-600">Loading verse details...</p>
        </div>
      </div>
    )
  }

  if (error || !verse) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 flex items-center justify-center">
        <div className="text-center max-w-md mx-auto p-8">
          <div className="text-6xl mb-4">😞</div>
          <h2 className="text-2xl font-bold text-gray-800 mb-2">Oops!</h2>
          <p className="text-gray-600 mb-6">{error || 'Verse not found'}</p>
          <button
            onClick={handleBack}
            className="btn-primary"
          >
            Go Back
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50">
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        {/* Back Button */}
        <button
          onClick={handleBack}
          className="mb-6 flex items-center gap-2 text-purple-600 hover:text-purple-800 font-medium transition"
        >
          <span className="text-xl">←</span>
          Back
        </button>

        {/* Main Verse Card */}
        <div className="bg-white rounded-xl shadow-lg p-8 mb-8 border-l-4 border-purple-500">
          <div className="text-center mb-6">
            <h1 className="text-4xl font-bold text-purple-700 mb-2">
              {verse.reference}
            </h1>
            <p className="text-sm text-gray-500 uppercase tracking-wide">
              {verse.translation || 'NIV'}
            </p>
          </div>

          <blockquote className="text-xl text-gray-800 leading-relaxed text-center italic mb-6 border-l-4 border-purple-200 pl-6">
            "{verse.text}"
          </blockquote>

          {/* Themes */}
          {verse.themes && verse.themes.length > 0 && (
            <div className="flex items-center justify-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-gray-600">Themes:</span>
              {verse.themes.map((theme, index) => (
                <span
                  key={index}
                  className="inline-block bg-blue-100 text-blue-700 px-4 py-1 rounded-full text-sm font-medium capitalize"
                >
                  {theme}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Context Section */}
        {verse.context && (
          <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
            <h2 className="text-2xl font-bold text-gray-800 mb-4 flex items-center gap-2">
              <span>📖</span>
              Context
            </h2>
            
            <div className="space-y-4">
              {verse.context.previousVerses && (
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <p className="text-sm font-semibold text-gray-600 mb-2">Previous Verses:</p>
                  <p className="text-gray-700 italic">...{verse.context.previousVerses}...</p>
                </div>
              )}
              
              <div className="bg-purple-50 rounded-lg p-4 border-2 border-purple-300">
                <p className="text-sm font-semibold text-purple-700 mb-2">Current Verse:</p>
                <p className="text-gray-800 font-medium">{verse.text}</p>
              </div>
              
              {verse.context.nextVerses && (
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <p className="text-sm font-semibold text-gray-600 mb-2">Following Verses:</p>
                  <p className="text-gray-700 italic">...{verse.context.nextVerses}...</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Related Verses Section */}
        {verse.relatedVerses && verse.relatedVerses.length > 0 && (
          <div className="bg-white rounded-xl shadow-lg p-8">
            <h2 className="text-2xl font-bold text-gray-800 mb-4 flex items-center gap-2">
              <span>🔗</span>
              Related Verses
            </h2>
            
            <div className="space-y-3">
              {verse.relatedVerses.map((related, index) => (
                <div
                  key={index}
                  onClick={() => handleRelatedVerseClick(related.reference)}
                  className="bg-gradient-to-r from-purple-50 to-blue-50 rounded-lg p-4 border border-purple-200 cursor-pointer hover:shadow-md transition-all hover:scale-[1.02]"
                >
                  <h3 className="font-bold text-purple-700 mb-1">{related.reference}</h3>
                  <p className="text-gray-700 text-sm italic">{related.preview}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer Navigation */}
        <div className="mt-8 text-center">
          <button
            onClick={() => navigate('/')}
            className="btn-primary"
          >
            Search More Verses
          </button>
        </div>
      </div>
    </div>
  )
}

export default VerseDetail
