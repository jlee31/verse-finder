/**
 * PromptInput Component - Simple text input for verse search
 */
import { useState } from 'react'

function PromptInput({ onSubmit, isLoading }) {
  const [prompt, setPrompt] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!prompt.trim()) return
    
    onSubmit({ mainPrompt: prompt.trim() })
    setPrompt('')
  }

  return (
    <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
      <form onSubmit={handleSubmit}>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="What's on your heart today? (e.g., 'I'm feeling anxious', 'I need guidance on relationships')"
          className="w-full p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none mb-4"
          rows={4}
          disabled={isLoading}
        />
        <div className="flex justify-center">
          <button
            type="submit"
            disabled={isLoading || !prompt.trim()}
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
