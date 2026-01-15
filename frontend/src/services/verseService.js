/**
 * API Service for Verse Finder
 * 
 * Handles all API calls to the backend Flask server
 * Currently uses placeholder/mock data - will connect to real backend when ready
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

/**
 * Find verses based on user prompt and context
 * @param {Object} data - { mainPrompt: string }
 * @returns {Promise<Object>} - Verse recommendations with metadata
 */
export const findVerses = async (data) => {
  try {
    const response = await fetch(`${API_BASE_URL}/verses/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`)
    }
    
    const result = await response.json()
    
    // For now, return mock data structure until backend processing is complete
    // The backend receives the data - you can process it and return verses
    return {
      success: true,
      verses: [],
      backend_response: result
    }
  } catch (error) {
    console.error('Error finding verses:', error)
    throw error
  }
}

/**
 * Get detailed information about a specific verse
 * @param {string} reference - Bible reference (e.g., "John 3:16")
 * @returns {Promise<Object>} - Detailed verse information
 */
export const getVerseDetails = async (reference) => {
  try {
    // TODO: Replace with actual API call
    // const response = await fetch(`${API_BASE_URL}/verses/${encodeURIComponent(reference)}`)
    // return await response.json()

    // Mock response
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve({
          success: true,
          verse: {
            reference: reference,
            text: 'For God so loved the world that he gave his one and only Son, that whoever believes in him shall not perish but have eternal life.',
            book: 'John',
            chapter: 3,
            verse: 16,
            translation: 'NIV',
            context: {
              previousVerses: 'Just as Moses lifted up the snake in the wilderness...',
              nextVerses: 'For God did not send his Son into the world to condemn the world...'
            },
            themes: ['salvation', 'love', 'faith'],
            relatedVerses: [
              { reference: 'Romans 5:8', preview: 'But God demonstrates his own love for us...' },
              { reference: '1 John 4:9', preview: 'This is how God showed his love among us...' }
            ]
          }
        })
      }, 800)
    })
  } catch (error) {
    console.error('Error getting verse details:', error)
    throw error
  }
}

/**
 * Generate AI reflection based on verses and user context
 * @param {Object} data - { verses: Array, userPrompt: string }
 * @returns {Promise<Object>} - AI-generated reflection
 */
export const generateReflection = async (data) => {
  try {
    // TODO: Replace with actual API call
    // const response = await fetch(`${API_BASE_URL}/reflection/generate`, {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify(data)
    // })
    // return await response.json()

    // Mock response
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve({
          success: true,
          reflection: {
            title: 'Finding Peace in Uncertain Times',
            content: 'God\'s word offers comfort and guidance when we face anxiety. These verses remind us that we are not alone in our struggles, and that through prayer and trust in Him, we can find the peace that surpasses understanding.',
            actionPoints: [
              'Take time each day to present your concerns to God in prayer',
              'Focus on today rather than worrying about tomorrow',
              'Trust that God is guiding your path, even when you can\'t see the way forward'
            ],
            encouragement: 'Remember, God cares deeply about your concerns and invites you to bring them to Him.'
          }
        })
      }, 1200)
    })
  } catch (error) {
    console.error('Error generating reflection:', error)
    throw error
  }
}

/**
 * Get verse recommendations by theme
 * @param {string} theme - Theme name (e.g., "peace", "love", "faith")
 * @returns {Promise<Object>} - Verses matching the theme
 */
export const getVersesByTheme = async (theme) => {
  try {
    // TODO: Replace with actual API call
    // const response = await fetch(`${API_BASE_URL}/verses/theme/${theme}`)
    // return await response.json()

    // Mock response
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve({
          success: true,
          theme: theme,
          verses: [
            {
              reference: 'Psalm 23:1',
              text: 'The LORD is my shepherd, I lack nothing.',
              relevanceScore: 0.98
            }
          ]
        })
      }, 600)
    })
  } catch (error) {
    console.error('Error getting verses by theme:', error)
    throw error
  }
}

export default {
  findVerses,
  getVerseDetails,
  generateReflection,
  getVersesByTheme
}
