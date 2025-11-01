/**
 * API Service for Verse Finder
 * 
 * Handles all API calls to the backend Flask server
 * Currently uses placeholder/mock data - will connect to real backend when ready
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api'

/**
 * Find verses based on user prompt and context
 * @param {Object} data - { mainPrompt: string, bulletPoints: string[] }
 * @returns {Promise<Object>} - Verse recommendations with metadata
 */
export const findVerses = async (data) => {
  try {
    // TODO: Replace with actual API call when backend is ready
    // const response = await fetch(`${API_BASE_URL}/verses/search`, {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify(data)
    // })
    // return await response.json()

    // Mock response for now
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve({
          success: true,
          verses: [
            {
              id: 1,
              reference: 'Philippians 4:6-7',
              text: 'Do not be anxious about anything, but in every situation, by prayer and petition, with thanksgiving, present your requests to God. And the peace of God, which transcends all understanding, will guard your hearts and your minds in Christ Jesus.',
              book: 'Philippians',
              chapter: 4,
              verse: '6-7',
              relevanceScore: 0.95,
              theme: 'peace'
            },
            {
              id: 2,
              reference: 'Matthew 6:34',
              text: 'Therefore do not worry about tomorrow, for tomorrow will worry about itself. Each day has enough trouble of its own.',
              book: 'Matthew',
              chapter: 6,
              verse: '34',
              relevanceScore: 0.92,
              theme: 'worry'
            },
            {
              id: 3,
              reference: 'Proverbs 3:5-6',
              text: 'Trust in the LORD with all your heart and lean not on your own understanding; in all your ways submit to him, and he will make your paths straight.',
              book: 'Proverbs',
              chapter: 3,
              verse: '5-6',
              relevanceScore: 0.89,
              theme: 'trust'
            }
          ],
          reflection: 'These verses speak to the heart of anxiety and worry, reminding us to trust in God\'s provision and peace.',
          timestamp: new Date().toISOString()
        })
      }, 1500)
    })
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
