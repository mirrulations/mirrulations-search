import { useState } from 'react'
import '../../styles/search-page.css'
import { searchDockets } from '../../api/searchApi'

function SearchPage() {
    const [query, setQuery] = useState('')
    const [filter, setFilter] = useState('')
    const [results, setResults] = useState([])

    const runSearch = async () => {
        const data = await searchDockets(query, filter)
        setResults(data)

    }

    const handleSubmit = (event) => {
        event.preventDefault()
        runSearch()
    }

    return (
        <div className="container">
            <h1>Mirrulations Explorer</h1>
            <form className="search-box" onSubmit={handleSubmit}>
                <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search query"/>
                <select value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter (optional)">
                    <option value=""> All</option>
                    <option value="Proposed Rule">Proposed Rule</option>
                    <option value="Final Rule">Final Rule</option>
                    <option value="Notice">Notice</option>
                </select>
                <button type="submit">Search</button>
            </form>

            <pre id = "output">{JSON.stringify(results, null, 2)}</pre>

        </div>
    )
}

export default SearchPage;

