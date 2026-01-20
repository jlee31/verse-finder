import { useState } from 'react'
import PromptInput from '../components/PromptInput'
import { findQuote } from '../services/verseService'

function Home() {
  const [isLoading, setIsLoading] = useState(false)
  const [quote, setQuote] = useState(null)

  const handleSubmitPrompt = async (submissionData) => {
    setIsLoading(true)
    setQuote(null)

    try {
      const result = await findQuote(submissionData.mainPrompt)
      setQuote(result)
    } catch (error) {
      console.error('Error:', error)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50">
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold text-gray-800 mb-4">
            Quote Finder
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Enter how you are feeling and we will try to match a quote to your feelings
          </p>
        </div>

        <PromptInput onSubmit={handleSubmitPrompt} isLoading={isLoading} />

        {quote && (
          <div className="mt-8 bg-white rounded-lg shadow-md p-6 border-l-4 border-purple-500">
            <blockquote className="text-xl text-gray-700 italic">
              "{quote}"
            </blockquote>
          </div>
        )}
      </div>
    </div>
  )
}

export default Home
