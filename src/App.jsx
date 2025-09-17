import { useState } from 'react'

function App() {
  const [count, setCount] = useState(0)

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-8">
        <h1 className="text-4xl font-bold text-center text-gray-800 mb-8">
          Christian Verse Finder
        </h1>
        
        <div className="max-w-md mx-auto bg-white rounded-lg shadow-lg p-10">
          <h2 className="text-2xl font-semibold text-gray-700 mb-4">
            Welcome to Your Verse Finder App
          </h2>
          
          <div className="text-center">
            <button
              onClick={() => setCount((count) => count + 1)}
              className="btn-primary text-lg px-8 py-3"
            >
              Count is {count}
            </button>
          </div>
          
          <div className="mt-6 p-4 bg-green-100 border border-green-300 rounded-lg">
            <p className="text-green-800 font-medium">
              ✅ Tailwind CSS is working! This green box proves it.
            </p>
          </div>
          
          <p className="text-gray-600 text-center mt-4">
            Your Christian app is ready to build! 🎉
          </p>
        </div>
      </div>
    </div>
  )
}

export default App