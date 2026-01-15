// home page

import { useState } from 'react'
import PromptInput from '../components/PromptInput'
import VerseCard from '../components/VerseCard'
import ReflectionCard from '../components/ReflectionCard'
import { findVerses, generateReflection } from '../services/verseService'

function Home() {
  const [isLoading, setIsLoading] = useState(false)
  const [reflection, setReflection] = useState(null)
  const [verses, setVerses] = useState([])

  const handleSubmitPrompt = async (submissionData) => {
    setIsLoading(true)
    setReflection(null)
    setVerses([])

    try {
      const result = await findVerses(submissionData)
      
      if (result.success) {
        setVerses(result.verses)
        
        const reflectionResult = await generateReflection({
          verses: result.verses,
          userPrompt: submissionData.mainPrompt
        })
        
        if (reflectionResult.success) {
          setReflection(reflectionResult.reflection)
        }
      }
    } catch (error) {
      console.error('Error processing prompt:', error)
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

        {(verses.length > 0 || reflection) && (
          <div className="space-y-6">
            {reflection && (
              <ReflectionCard reflection={reflection} verses={verses} />
            )}
            
            {verses.length > 0 && (
              <div>
                <h2 className="text-2xl font-semibold text-gray-800 mb-4">
                  Recommended Quote
                </h2>
                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                  {verses.map((verse) => (
                    <VerseCard key={verse.id} verse={verse} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default Home
