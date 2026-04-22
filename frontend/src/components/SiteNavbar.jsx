import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { motion } from "motion/react";
import { BooksIcon } from "@phosphor-icons/react";
import { getAuthStatus } from "../api/searchApi";
import "../styles/Home.css";

const MotionLink = motion.create(Link);

const navVariants = {
  hidden: { y: -100, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
    transition: { type: "spring", stiffness: 260, damping: 28 },
  },
};

const handleGoogleLogin = () => {
  const confirmed = window.confirm(
    "This application is in testing beta. Only authorized users can access it. Continue?"
  );

  if (confirmed) {
    window.location.href = "/auth/login";
  }
};

/**
 * @param {"dark" | "light"} theme — dark on home hero; white bar on app / legal / login
 * @param {"full" | "app"} [layout] — full: marketing + Search + Privacy; app: Home (+ Search on collections only)
 * @param {() => void} [onCheckDownloads] — when set and user is signed in, shows Check Downloads (collections flow)
 * @param {boolean} [showCollectionsLink] — My Collections link (search / explorer page)
 */
export default function SiteNavbar({ theme = "dark", layout = "full", onCheckDownloads, showCollectionsLink = false }) {
  const { pathname } = useLocation();
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const aboutHref = pathname === "/" ? "#about" : "/#about";
  const featuresHref = pathname === "/" ? "#features" : "/#features";

  useEffect(() => {
    getAuthStatus()
      .then((data) => {
        if (data.logged_in) {
          setUser({ name: data.name, email: data.email });
        } else {
          setUser(null);
        }
      })
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, []);

  const navClass =
    theme === "light" ? "home-navbar home-navbar--light" : "home-navbar";

  return (
    <motion.header className={navClass} role="banner" variants={navVariants} initial="hidden" animate="visible">
      <MotionLink to="/" className="home-nav-brand">
        Mirrulations
      </MotionLink>
      <nav className="home-nav-links" aria-label="Main navigation">
        {layout === "app" ? (
          <>
            <MotionLink to="/" className="home-nav-link" whileHover={{ y: -1 }} whileTap={{ scale: 0.98 }}>
              Home
            </MotionLink>
            {pathname === "/collections" ? (
              <MotionLink to="/explorer" className="home-nav-link" whileHover={{ y: -1 }} whileTap={{ scale: 0.98 }}>
                Search
              </MotionLink>
            ) : null}
          </>
        ) : (
          <>
            <motion.a href={aboutHref} className="home-nav-link" whileHover={{ y: -1 }} whileTap={{ scale: 0.98 }}>
              About
            </motion.a>
            <motion.a href={featuresHref} className="home-nav-link" whileHover={{ y: -1 }} whileTap={{ scale: 0.98 }}>
              Features
            </motion.a>
            <MotionLink to="/explorer" className="home-nav-link" whileHover={{ y: -1 }} whileTap={{ scale: 0.98 }}>
              Search
            </MotionLink>
            <MotionLink to="/privacy" className="home-nav-link" whileHover={{ y: -1 }} whileTap={{ scale: 0.98 }}>
              Privacy Policy
            </MotionLink>
          </>
        )}
        {!authLoading && user ? (
          <>
            {showCollectionsLink ? (
              <MotionLink
                to="/collections"
                className="home-nav-link home-nav-link--collections"
                whileHover={{ y: -1 }}
                whileTap={{ scale: 0.98 }}
              >
                <BooksIcon size={20} weight="duotone" aria-hidden />
                My Collections
              </MotionLink>
            ) : null}
            {typeof onCheckDownloads === "function" ? (
              <motion.button
                type="button"
                className="home-nav-link home-nav-link--as-button"
                whileHover={{ y: -1 }}
                whileTap={{ scale: 0.98 }}
                onClick={onCheckDownloads}
              >
                Check Downloads
              </motion.button>
            ) : null}
            <span className="home-nav-signout-group">
              <span className="home-nav-user" title={user.email}>
                {(user.name || user.email || "").trim() || "Account"}
              </span>
              <motion.a href="/logout" className="home-nav-link home-nav-link--ghost" whileHover={{ y: -1 }} whileTap={{ scale: 0.98 }}>
                Sign out
              </motion.a>
            </span>
          </>
        ) : !authLoading ? (
          <motion.button onClick={handleGoogleLogin} className="home-nav-google" whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
            <span className="home-nav-google-icon" aria-hidden>
              <svg viewBox="0 0 24 24" width={18} height={18}>
                <path fill="#EA4335" d="M12 5.04c1.55 0 2.96.54 4.07 1.6l3.03-3.03C17.5 2.32 14.9 1 12 1 7.58 1 3.84 3.47 2.1 7.05l3.51 2.72A6.98 6.98 0 0 1 12 5.04z" />
                <path fill="#4285F4" d="M22.5 12.23c0-.82-.07-1.6-.22-2.36H12v4.51h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.09-1.92 3.22-4.74 3.22-8.23z" />
                <path fill="#FBBC05" d="M5.61 14.08A7.02 7.02 0 0 1 5.04 12c0-.72.13-1.41.35-2.08L2.1 7.05A11.95 11.95 0 0 0 1 12c0 1.93.46 3.76 1.27 5.38l3.34-2.6z" />
                <path fill="#34A853" d="M12 23c3.24 0 5.97-1.08 7.96-2.93l-3.57-2.77c-.99.67-2.26 1.07-4.39 1.07-2.39 0-4.42-.81-5.89-2.18l-3.51 2.72C6.97 21.16 9.24 23 12 23z" />
              </svg>
            </span>
            Sign in with Google
          </motion.button>
        ) : null}
      </nav>
    </motion.header>
  );
}
