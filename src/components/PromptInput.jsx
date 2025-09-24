/**
 * PromptInput Component
 * 
 * Handles user input for spiritual questions and bullet points
 * Features: main prompt textarea, dynamic bullet point management
 */
import { useState } from 'react'

function PromptInput({ onSubmit, isLoading }) {
  const [prompt, setPrompt] = useState('') // Main spiritual question
  const [bulletPoints, setBulletPoints] = useState([]) // Array of additional points
  const [newPoint, setNewPoint] = useState('') // Current bullet point being typed

  const handleAddPoint = (e) => {
    e.preventDefault()
    if (!newPoint.trim()) return
    setBulletPoints(prev => [...prev, newPoint.trim()])
    setNewPoint('')
  }

  const handleRemovePoint = (index) => {
    setBulletPoints(prev => prev.filter((_, i) => i !== index))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!prompt.trim() && bulletPoints.length === 0) return
    
    const submissionData = {
      mainPrompt: prompt.trim(),
      bulletPoints: bulletPoints
    }
    
    onSubmit(submissionData)
    setPrompt('')
    setBulletPoints([])
  }

  return (
    <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
      <h2 className="text-2xl font-semibold text-gray-800 mb-6 text-center">
        What's on your heart today?
      </h2>
      
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Main Prompt */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Your main question or concern:
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g., 'I'm feeling anxious about the future', 'I need guidance on relationships', 'I want to understand forgiveness'..."
            className="w-full p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
            rows={3}
            disabled={isLoading}
          />
        </div>

        {/* Bullet Points Section */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Additional thoughts or specific points:
          </label>
          
          {/* Add new bullet point */}
          <form onSubmit={handleAddPoint} className="flex gap-2 mb-3">
            <input
              type="text"
              value={newPoint}
              onChange={(e) => setNewPoint(e.target.value)}
              placeholder="Add a specific point..."
              className="flex-1 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading || !newPoint.trim()}
              className="px-4 py-3 bg-blue-100 hover:bg-blue-200 text-blue-700 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Add
            </button>
          </form>

          {/* Display bullet points */}
          {bulletPoints.length > 0 && (
            <div className="space-y-2">
              {bulletPoints.map((point, index) => (
                <div key={index} className="flex items-center gap-2 p-3 bg-blue-50 rounded-lg border border-blue-200">
                  <span className="text-blue-600 font-bold">•</span>
                  <span className="flex-1 text-gray-700">{point}</span>
                  <button
                    onClick={() => handleRemovePoint(index)}
                    className="text-red-500 hover:text-red-700 p-1"
                    disabled={isLoading}
                    title="Remove this point"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        
        <div className="flex justify-center">
          <button
            type="submit"
            disabled={isLoading || (!prompt.trim() && bulletPoints.length === 0)}
            className="btn-primary text-lg px-8 py-3 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isLoading ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                Finding Verses...
              </>
            ) : (
              'Find Verses'
            )}
          </button>
        </div>
      </form>
    </div>
  )
}

export default PromptInput
