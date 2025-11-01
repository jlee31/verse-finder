/**
 * Home Page Component
 * 
 * Main page for the verse finder application
 * Features: prompt input, verse search results, reflection display
 */
import { useState } from 'react'
import PromptInput from '../components/PromptInput'
import PromptList from '../components/PromptList'
import VerseCard from '../components/VerseCard'
import ReflectionCard from '../components/ReflectionCard'
import { findVerses, generateReflection } from '../services/verseService'

function Home() {
  const [prompts, setPrompts] = useState([]) // Array of user prompts with results
  const [isLoading, setIsLoading] = useState(false) // Loading state for ML processing
  const [currentReflection, setCurrentReflection] = useState(null) // Current AI reflection
  const [currentVerses, setCurrentVerses] = useState([]) // Current verse results

  /**
   * Handles prompt submission and verse retrieval
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

    try {
      // Call verse finding service
      const result = await findVerses(submissionData)
      
      if (result.success) {
        // Update the prompt with results
        setPrompts(prev => prev.map(p => 
          p.id === promptData.id 
            ? { ...p, status: 'completed', verses: result.verses, reflection: result.reflection }
            : p
        ))
        
        // Set current results for display
        setCurrentVerses(result.verses)
        
        // Generate reflection
        const reflectionResult = await generateReflection({
          verses: result.verses,
          userPrompt: submissionData.mainPrompt
        })
        
        if (reflectionResult.success) {
          setCurrentReflection(reflectionResult.reflection)
        }
      }
    } catch (error) {
      console.error('Error processing prompt:', error)
      setPrompts(prev => prev.map(p => 
        p.id === promptData.id 
          ? { ...p, status: 'error', error: 'Failed to retrieve verses' }
          : p
      ))
    } finally {
      setIsLoading(false)
    }
  }

  const handleDeletePrompt = (id) => {
    setPrompts(prev => prev.filter(p => p.id !== id))
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50">
      <div className="container mx-auto px-4 py-8 max-w-6xl">
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

        {/* Current Results Section */}
        {(currentVerses.length > 0 || currentReflection) && (
          <div className="mb-12 space-y-6">
            <h2 className="text-3xl font-bold text-gray-800 text-center">
              Your Results
            </h2>
            
            {/* Reflection Card */}
            {currentReflection && (
              <ReflectionCard reflection={currentReflection} verses={currentVerses} />
            )}
            
            {/* Verse Cards Grid */}
            {currentVerses.length > 0 && (
              <div>
                <h3 className="text-2xl font-semibold text-gray-800 mb-4">
                  Recommended Verses
                </h3>
                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                  {currentVerses.map((verse) => (
                    <VerseCard key={verse.id} verse={verse} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Recent Searches Section */}
        <div className="space-y-6">
          <h3 className="text-2xl font-semibold text-gray-800 text-center">
            Your Recent Searches
          </h3>
          
          <PromptList prompts={prompts} onDeletePrompt={handleDeletePrompt} />
        </div>

        {/* Footer Info */}
        <div className="mt-12 text-center">
          <div className="bg-gradient-to-r from-green-100 to-emerald-100 border border-green-300 rounded-lg p-4 max-w-md mx-auto">
            <p className="text-green-800 font-medium">
              ✅ Frontend ready! Backend integration coming soon.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Home
