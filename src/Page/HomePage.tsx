import { useNavigate } from "react-router-dom";
import "../CSS/Page.css";
import "../CSS/Home.css"
import { useEffect, useRef, useState } from "react";
import { GiF1Car } from "react-icons/gi";

function HomePage() {

  const navigate = useNavigate();
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const [isFacingLeft, setIsFacingLeft] = useState(false);
  const [isVisible, setIsVisible] = useState(false);
  const prevXRef = useRef(0);

  useEffect(() => {

    const handleMouseMove = (e: MouseEvent) => {
      if (!isVisible) setIsVisible(true);

      if (e.clientX < prevXRef.current) setIsFacingLeft(true);
      else if (e.clientX > prevXRef.current) setIsFacingLeft(false);
      
      prevXRef.current = e.clientX; 
      setMousePosition({ x: e.clientX, y: e.clientY });
    };

    const handleMouseLeave = () => setIsVisible(false);

    window.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseleave", handleMouseLeave);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
    };
  }, [isVisible]);

  return (
    <div className="home-container">
      
      {/*  Hero Section  */}
      <section className="hero-section">
        <h1 className="hero-title">Welcome to <span>F1 Laboratory</span></h1>
        <p className="hero-subtitle">
          Data Science for Formula 1 data
        </p>
        <a href="https://github.com/ImMasterSam/F1-Laboratory" target="_blank" rel="noreferrer" className="github-btn">
          View on GitHub
        </a>
      </section>

      {/* Quick Links */}
      <section className="quick-links-section">
        <div className="links-grid">
          
          <div className="link-card" onClick={() => navigate('/livetiming')}>
            <div className="card-header">
              <h2>Session Replay</h2>
            </div>
            <p>Historical race replays, lap times, and telemetry data.</p>
          </div>

          <div className="link-card" onClick={() => navigate('/schedule')}>
            <h2>Race Schedule</h2>
            <p>Full season calendar, track layouts, and session times.</p>
          </div>

          <div className="link-card" onClick={() => navigate('/standings/drivers')}>
            <h2>Driver Standings</h2>
            <p>Current championship points and points evolution.</p>
          </div>

          <div className="link-card" onClick={() => navigate('/standings/constructors')}>
            <h2>Constructor Standings</h2>
            <p>Team championship points and head-to-head battles.</p>
          </div>

        </div>
      </section>

      <div 
        className="mouse-car" 
        style={{
          // 定位跟隨
          left: mousePosition.x + 'px',
          top: mousePosition.y + 'px',
          opacity: isVisible ? 1 : 0,
          transform: isFacingLeft ? 'translate(-50%, -50%) scaleX(-1)' : 'translate(-50%, -50%)',
          
        }}
      >
        {/* 給點紅色與陰影，看起來更有感覺 */}
        <GiF1Car size={60} color="#e10600" style={{ filter: 'drop-shadow(0 0 5px rgba(225, 6, 0, 0.5))' }} />
      </div>

      {/* Footer */}
      <footer className="home-footer">
        This website is unofficial and is not associated in any way with the Formula 1 companies. F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP, GRAND PRIX and related marks are trademarks of Formula One Licensing B.V.
      </footer>
      
    </div>

  );
}

export default HomePage;
