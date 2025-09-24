import { useState } from 'react'
import PromptInput from './components/PromptInput'
import PromptList from './components/PromptList'

/**
 * Main App Component - Christian Verse Finder
 * 
 * Manages the overall application state including:
 * - User prompts and bullet points
 * - Loading states during ML processing
 * - API integration ready for Python backend
 */
function App() {
  const [prompts, setPrompts] = useState([]) // Array of user prompts with results
  const [isLoading, setIsLoading] = useState(false) // Loading state for ML processing

  /**
   * Handles prompt submission and ML processing
   * Currently simulates API call - replace setTimeout with real Python backend call
   */
  const handleSubmitPrompt = async (submissionData) => {
    setIsLoading(true)
    
    // Create prompt data structure
    const promptData = {
      id: Date.now(),
      mainPrompt: submissionData.mainPrompt,
      bulletPoints: submissionData.bulletPoints,
      timestamp: new Date().toLocaleString(),
      status: 'processing'
    }
    
    setPrompts(prev => [promptData, ...prev])

    // TODO: Replace with actual API call to Python ML backend
    setTimeout(() => {
      setPrompts(prev => prev.map(p => 
        p.id === promptData.id 
          ? { ...p, status: 'completed', verses: ['Placeholder verse result - ML model will be integrated here'] }
          : p
      ))
      setIsLoading(false)
    }, 2000)
  }

  const handleDeletePrompt = (id) => {
    setPrompts(prev => prev.filter(p => p.id !== id))
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50">
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold text-gray-800 mb-4 bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            Christian Verse Finder
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Enter your spiritual questions or topics to find meaningful Bible verses
          </p>
        </div>

        {/* Prompt Input Form */}
        <PromptInput onSubmit={handleSubmitPrompt} isLoading={isLoading} />

        {/* Prompts List */}
        <div className="space-y-6">
          <h3 className="text-2xl font-semibold text-gray-800 text-center">
            Your Recent Searches
          </h3>
          
          <PromptList prompts={prompts} onDeletePrompt={handleDeletePrompt} />
        </div>

        {/* Footer Info */}
        <div className="mt-12 text-center">
          <div className="bg-green-100 border border-green-300 rounded-lg p-4 max-w-md mx-auto">
            <p className="text-green-800 font-medium">
              ✅ React app ready! Python ML backend integration coming soon.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App