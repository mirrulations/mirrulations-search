import React from 'react'
import { useNavigate } from 'react-router-dom'
const HomePage = () => {
    const navigate = useNavigate()

    return (
        <div>
            <h1>Landing Page</h1>
            <button onClick={() => navigate("/searchpage")}>
                Click Me
            </button>
        </div>
    )
}

export default HomePage
