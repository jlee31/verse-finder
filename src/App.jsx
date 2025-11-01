/**
 * Main App Component - Christian Verse Finder
 * 
 * Sets up routing for the application
 * Routes:
 * - / : Home page with verse search
 * - /verse/:reference : Detailed verse view
 */
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import VerseDetail from './pages/VerseDetail'

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/verse/:reference" element={<VerseDetail />} />
      </Routes>
    </Router>
  )
}

export default App
