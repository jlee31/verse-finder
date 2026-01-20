const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export const findQuote = async (prompt) => {
  const response = await fetch(`${API_BASE_URL}/verses/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mainPrompt: prompt })
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }

  const data = await response.json()
  return data.received_data.quote
}
