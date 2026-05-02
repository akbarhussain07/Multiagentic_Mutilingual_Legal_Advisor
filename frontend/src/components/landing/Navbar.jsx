import React, { useState, useEffect } from 'react';
import { Scale, Menu, X } from 'lucide-react';
import './Navbar.css';

export const Navbar = () => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navLinks = [
    { name: 'Home', href: '#' },
    { name: 'Features', href: '#features' },
    { name: 'How it Works', href: '#how-it-works' },
    { name: 'Disclaimer', href: '#disclaimer' },
  ];

  return (
    <nav className={`navbar ${isScrolled ? 'navbar--scrolled' : 'navbar--transparent'}`}>
      <div className="navbar__container">
        <div className="navbar__content">
          
          {/* Logo */}
          <div className="navbar__logo">
            <div className="navbar__logo-icon">
              <Scale color="white" size={24} />
            </div>
            <span className="navbar__logo-text">Legal Advisor</span>
          </div>

          {/* Desktop Links */}
          <div className="navbar__menu">
            {navLinks.map((link) => (
              <a key={link.name} href={link.href} className="navbar__link">
                {link.name}
              </a>
            ))}
          </div>

          {/* Desktop CTA */}
          <div className="navbar__cta-desktop">
           <a href="/signup"> <button className="navbar__btn navbar__btn--desktop" >
              Get Started
            </button></a>
          </div>

          {/* Mobile Menu Button */}
          <button 
            className="navbar__mobile-toggle"
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          >
            {isMobileMenuOpen ? <X size={28} /> : <Menu size={28} />}
          </button>
        </div>
      </div>

      {/* Mobile Menu Dropdown */}
      {isMobileMenuOpen && (
        <div className="mobile-menu">
          <div className="mobile-menu__content">
            {navLinks.map((link) => (
              <a 
                key={link.name} 
                href={link.href} 
                className="navbar__link"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                {link.name}
              </a>
            ))}
            <a href="/signup"><button className="navbar__btn" style={{ background: '#22d3ee', color: '#000', border: 'none' }}>
              Get Started
            </button></a>
          </div>
        </div>
      )}
    </nav>
  );
};