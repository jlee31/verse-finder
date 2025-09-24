/**
 * PromptList Component
 * 
 * Displays all user prompts with their results
 * Shows empty state when no prompts exist
 */
import PromptItem from './PromptItem'

function PromptList({ prompts, onDeletePrompt }) {
  if (prompts.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-gray-400 text-6xl mb-4">📖</div>
        <p className="text-gray-500 text-lg">
          No prompts yet. Start by asking a question above!
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {prompts.map((prompt) => (
        <PromptItem 
          key={prompt.id} 
          prompt={prompt} 
          onDelete={() => onDeletePrompt(prompt.id)} 
        />
      ))}
    </div>
  )
}

export default PromptList
