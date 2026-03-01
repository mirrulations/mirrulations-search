import React from 'react'
import '../styles/LogIn.css'
import { motion } from "motion/react"

const LogIn = () => {
    return (
        <motion.div className="login-wrapper"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, duration: 1.5, ease: "easeInOut" }}
        >
            <div className="login-box floating-effect">
                <motion.h2
                 initial={{ opacity: 0, y: -20 }}
                 animate={{ opacity: 1, y: 0 }}
                 transition={{ delay: 0.7, duration: 1, ease: "easeInOut" }}
                >LOG IN</motion.h2>
                <div className='inputs-div'>
                    <motion.input type="email" placeholder="Email"
                     initial={{ opacity: 0, y: -20 }}
                     animate={{ opacity: 1, y: 0 }}
                     transition={{ delay: 1.2, duration: 1, ease: "easeInOut" }}
                    />
                    <motion.input type="password" placeholder="Password" 
                     initial={{ opacity: 0, y: -20 }}
                     animate={{ opacity: 1, y: 0 }}
                     transition={{ delay: 1.6, duration: 1, ease: "easeInOut" }}
                    />
                    <button>LOG IN</button>
                </div>
            </div>
        </motion.div>
    )
}

export default LogIn