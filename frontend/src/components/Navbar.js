import React from 'react';
import { AppBar, Toolbar, Typography, Button, Box } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

const pages = [
  { label: 'Home', path: '/' },
  { label: 'Opportunities', path: '/opportunities' },
  { label: 'Saved', path: '/saved' },
  { label: 'Profile', path: '/profile' },
  { label: 'Resume Match', path: '/resume-match' },
  { label: 'Map', path: '/map' },
  { label: 'AI Email', path: '/ai-email' },
  { label: 'Admin', path: '/admin' },
  { label: 'Login', path: '/login' },
  { label: 'Signup', path: '/signup' },
];

function Navbar() {
  return (
    <AppBar position="static" color="primary" elevation={2}>
      <Toolbar>
        <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 800, letterSpacing: 1 }}>
          VolunteerHub
        </Typography>
        <Box>
          {pages.map((page) => (
            <Button
              key={page.path}
              color="inherit"
              component={RouterLink}
              to={page.path}
              sx={{ fontWeight: 600, mx: 0.5 }}
            >
              {page.label}
            </Button>
          ))}
        </Box>
      </Toolbar>
    </AppBar>
  );
}

export default Navbar; 