import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import SearchPage from './pages/search-page/SearchPage';
import HomePage from './pages/home-page.jsx/HomePage';

function App() {
  return (
    <Router basename="/static">
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/searchpage" element={<SearchPage />} />

      </Routes>
    </Router>
  );
}

export default App;