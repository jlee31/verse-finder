// Individual prompt item component with verse results
function PromptItem({ prompt, onDelete }) {
  return (
    <div className="bg-white rounded-lg shadow-md p-6 border-l-4 border-blue-500">
      <div className="flex justify-between items-start mb-4">
        <div className="flex-1">
          {prompt.mainPrompt && (
            <p className="text-gray-800 font-medium mb-2">{prompt.mainPrompt}</p>
          )}
          {prompt.bulletPoints && prompt.bulletPoints.length > 0 && (
            <div className="mb-3">
              <ul className="space-y-1">
                {prompt.bulletPoints.map((point, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <span className="text-blue-600 font-bold mt-0.5">•</span>
                    <span className="text-gray-700 text-sm">{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-sm text-gray-500">{prompt.timestamp}</p>
        </div>
        <button
          onClick={onDelete}
          className="text-red-500 hover:text-red-700 ml-4 p-1 hover:bg-red-50 rounded"
          title="Delete prompt"
        >
          ✕
        </button>
      </div>
      
      <div className="border-t pt-4">
        {prompt.status === 'processing' ? (
          <div className="flex items-center text-blue-600">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
            Processing with AI model...
          </div>
        ) : (
          <div>
            <h4 className="font-semibold text-gray-700 mb-2">Suggested Verses:</h4>
            <div className="space-y-2">
              {prompt.verses?.map((verse, index) => (
                <div key={index} className="bg-blue-50 p-3 rounded-lg border border-blue-200">
                  <p className="text-gray-700 italic">"{verse}"</p>
                  <p className="text-sm text-blue-600 mt-1">- John 3:16 (Example)</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default PromptItem
