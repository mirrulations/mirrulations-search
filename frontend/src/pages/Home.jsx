import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { getAuthStatus } from "../api/searchApi";
import SiteNavbar from "../components/SiteNavbar";
import "../styles/Home.css";

import hero from "../assets/hero.jpg";

const MotionLink = motion.create(Link);

const heroContainerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.14, delayChildren: 0.15 },
  },
};

const heroItemVariants = {
  hidden: { opacity: 0, y: 28 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: "spring", stiffness: 220, damping: 22 },
  },
};

const sectionVariants = {
  hidden: { opacity: 0, y: 40 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] },
  },
};

const buttonMotion = {
  rest: { scale: 1 },
  hover: { scale: 1.04, transition: { type: "spring", stiffness: 400, damping: 18 } },
  tap: { scale: 0.97 },
};

const cardReveal = {
  hidden: { opacity: 0, y: 20 },
  visible: (i) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  }),
};

export default function Home() {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  useEffect(() => {
    getAuthStatus()
      .then((data) => {
        if (data.logged_in) {
          setUser({ name: data.name, email: data.email });
        }
      })
      .finally(() => setAuthLoading(false));
  }, []);

  return (
    <div className="home-page">
      <SiteNavbar theme="dark" />

      <section
        className="home-hero"
        style={{
          backgroundImage: `linear-gradient(120deg, rgba(15,23,42,0.78) 0%, rgba(30,27,75,0.58) 45%, rgba(15,23,42,0.4) 100%), url(${hero})`,
        }}
      >
        <motion.div
          className="hero-text-container"
          variants={heroContainerVariants}
          initial="hidden"
          animate="visible"
        >
          <motion.h1 className="hero-title" variants={heroItemVariants}>
            Search U.S. federal
            <br />
            <span className="hero-title-accent">regulatory dockets</span>
          </motion.h1>
          <motion.p className="hero-lead" variants={heroItemVariants}>
            Mirrulations Explorer helps you find rulemakings and related documents from public U.S. federal sources. Sign
            in to search, save dockets you care about, and use downloads when your administrator enables them.
          </motion.p>
          <motion.div className="hero-buttons" variants={heroItemVariants}>
            <MotionLink
              to="/explorer"
              className="hero-btn hero-btn--primary"
              variants={buttonMotion}
              initial="rest"
              whileHover="hover"
              whileTap="tap"
            >
              Get started
            </MotionLink>
            <MotionLink
              to="/privacy"
              className="hero-btn hero-btn--outline"
              variants={buttonMotion}
              initial="rest"
              whileHover="hover"
              whileTap="tap"
            >
              Privacy Policy
            </MotionLink>
          </motion.div>
        </motion.div>
      </section>

      <motion.main
        className="home-body"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-60px" }}
        variants={sectionVariants}
      >
        <section id="about" className="home-section home-section--narrow">
          <motion.h2 className="home-section-heading" initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.4 }}>
            What this is
          </motion.h2>
          <motion.p className="home-section-lead" initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ delay: 0.05, duration: 0.45 }}>
            A straightforward way to explore federal docket data: search by keywords and filters, open dockets and
            documents, and keep a personal list when you are signed in.
          </motion.p>
        </section>

        <section id="features" className="home-section home-section--wide">
          <motion.h2 className="home-section-heading home-section-heading--center" initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.4 }}>
            What you can do
          </motion.h2>
          <div className="home-feature-grid">
            {[
              {
                title: "Search and filter",
                body: "Find dockets and documents with text search and options such as agency, date range, and status.",
              },
              {
                title: "Save what you follow",
                body: "When you are signed in, you can keep dockets in your account so you can return to them later.",
              },
              {
                title: "Stay in control",
                body: "We only use your Google account to sign you in and run the features you use. See the Privacy Policy for details.",
              },
            ].map((card, i) => (
              <motion.article key={card.title} className="home-feature-card" custom={i} initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-30px" }} variants={cardReveal}>
                <h3>{card.title}</h3>
                <p>{card.body}</p>
              </motion.article>
            ))}
          </div>
        </section>

        <section className="home-section home-section--wide">
          <motion.div className="home-cta-card" initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5 }}>
            <h2>Ready to search?</h2>
            {!authLoading && user ? (
              <>
                <p>You are signed in. Open search to look up dockets and documents.</p>
                <div className="home-cta-row">
                  <MotionLink to="/explorer" className="home-cta-primary" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                    Search Tool
                  </MotionLink>
                  <MotionLink to="/privacy" className="home-cta-secondary" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                    Privacy Policy
                  </MotionLink>
                </div>
              </>
            ) : (
              <>
                <p>Sign in with Google to open the search experience.</p>
                <div className="home-cta-row">
                  <MotionLink to="/login" className="home-cta-primary" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                    Sign in
                  </MotionLink>
                  <MotionLink to="/privacy" className="home-cta-secondary" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                    Privacy Policy
                  </MotionLink>
                </div>
              </>
            )}
          </motion.div>
        </section>

        <motion.footer className="home-page-footer" initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ duration: 0.45 }}>
          <span>Mirrulations Explorer</span>
          <span className="home-page-footer-dot" aria-hidden>·</span>
          <Link to="/privacy">Privacy Policy</Link>
          <span className="home-page-footer-dot" aria-hidden>·</span>
          <a href="/admin" className="home-footer-admin-link">Admin</a>
        </motion.footer>
      </motion.main>
    </div>
  );
}
