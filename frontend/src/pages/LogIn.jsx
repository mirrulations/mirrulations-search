import React from 'react'
import '../styles/LogIn.css'

const LogIn = () => {
  return (
    <div className="login-wrapper">
      <div className="login-box">
        <h2>Log In</h2>

        <input type="email" placeholder="Email" />
        <input type="password" placeholder="Password" />

        <button>Log In</button>
      </div>
    </div>
  )
}

export default LogIn