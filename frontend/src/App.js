import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import Opportunities from './pages/Opportunities';
import Profile from './pages/Profile';
import AdminDashboard from './pages/AdminDashboard';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Saved from './pages/Saved';
import ResumeMatch from './pages/ResumeMatch';
import Map from './pages/Map';
import AIEmail from './pages/AIEmail';
import Navbar from './components/Navbar';
import { Box } from '@mui/material';

function App() {
  return (
    <Box sx={{ minHeight: '100vh', background: 'background.default' }}>
      <Navbar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/opportunities" element={<Opportunities />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/saved" element={<Saved />} />
        <Route path="/resume-match" element={<ResumeMatch />} />
        <Route path="/map" element={<Map />} />
        <Route path="/ai-email" element={<AIEmail />} />
      </Routes>
    </Box>
  );
}

export default App; 